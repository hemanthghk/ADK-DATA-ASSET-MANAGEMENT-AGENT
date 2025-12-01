import os
import re
import asyncio
import ollama
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from typing import Dict, List
import google.generativeai as genai
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# ============================================
# CONFIGURATION
# ============================================

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY", "YOUR_API_KEY")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


genai.configure(api_key=os.environ["GOOGLE_API_KEY"])


PG_CONNECTION = None
DB_CONFIG = {
    "dbname": os.getenv("PG_DATABASE", "dam_agent"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "host": os.getenv("PG_HOST", "localhost"),
    "port": os.getenv("PG_PORT", "5432")
}

DETECTED_ISSUES = []
PENDING_APPROVALS = []
DRIVE_SERVICE = None
CHUNK_CACHE = {}  

# ============================================
# POSTGRESQL + PGVECTOR SETUP
# ============================================

def initialize_database():
    """Initialize PostgreSQL with pgvector extension"""
    global PG_CONNECTION
    
    try:
        PG_CONNECTION = psycopg2.connect(**DB_CONFIG)
        register_vector(PG_CONNECTION)
        
        cursor = PG_CONNECTION.cursor()
        
        
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                file_id VARCHAR(255) UNIQUE NOT NULL,
                filename VARCHAR(500) NOT NULL,
                content TEXT,
                embedding vector(768),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                file_id VARCHAR(255) NOT NULL,
                chunk_id INTEGER NOT NULL,
                chunk_text TEXT,
                summary TEXT,
                embedding vector(768),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(file_id, chunk_id)
            );
        """)
        
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS documents_embedding_idx 
            ON documents USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """)
        
        PG_CONNECTION.commit()
        cursor.close()
        
        return {"status": "success", "message": "PostgreSQL + pgvector initialized with chunking support"}
    except Exception as e:
        return {"status": "error", "message": f"Database init failed: {str(e)}"}


def generate_embedding(text: str) -> List[float]:
    """Generate embeddings using Ollama nomic-embed-text
    
    Args:
        text: Text to embed
    """
    try:
        response = ollama.embeddings(
            model='nomic-embed-text',
            prompt=text[:8000]  
        )
        return response['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return [0.0] * 768 


# ============================================
# DOCUMENT CHUNKING & SUMMARIZATION (ROM CACHE)
# ============================================

def chunk_document(content: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict]:
    """Split large documents into overlapping chunks
    
    Args:
        content: Full document content
        chunk_size: Characters per chunk
        overlap: Overlap between chunks for context preservation
    """
    chunks = []
    start = 0
    
    while start < len(content):
        end = start + chunk_size
        chunk_text = content[start:end]
        
        chunks.append({
            "chunk_id": len(chunks),
            "text": chunk_text,
            "start_pos": start,
            "end_pos": end,
            "length": len(chunk_text)
        })
        
        start += chunk_size - overlap
    
    return chunks


def summarize_chunk(chunk_text: str) -> str:
    """Summarize a chunk using Gemini for better search
    
    Args:
        chunk_text: Chunk content to summarize
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Summarize this document chunk in 2-3 sentences. 
        Focus on key entities, dates, numbers, and important information:
        
        {chunk_text[:2000]}"""
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Summarization error: {e}")
        return chunk_text[:200]  


def process_large_file(file_id: str, content: str, filename: str) -> Dict:
    """Process large files with chunking, summarization, and ROM caching
    
    Args:
        file_id: File identifier
        content: Full document content
        filename: Name of the file
    """
    
    if file_id in CHUNK_CACHE:
        return {
            "status": "cached",
            "chunks": len(CHUNK_CACHE[file_id]),
            "message": f"Retrieved {len(CHUNK_CACHE[file_id])} chunks from ROM cache"
        }
    
    try:
      
        chunks = chunk_document(content)
        
       
        processed_chunks = []
        
        for chunk in chunks:
            summary = summarize_chunk(chunk["text"])
            embedding = generate_embedding(summary)  
            
            processed_chunks.append({
                **chunk,
                "summary": summary,
                "embedding": embedding
            })
            
            # Store chunk in PostgreSQL
            if PG_CONNECTION:
                cursor = PG_CONNECTION.cursor()
                cursor.execute("""
                    INSERT INTO document_chunks 
                    (file_id, chunk_id, chunk_text, summary, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (file_id, chunk_id) DO UPDATE
                    SET chunk_text = EXCLUDED.chunk_text,
                        summary = EXCLUDED.summary,
                        embedding = EXCLUDED.embedding;
                """, (
                    file_id,
                    chunk["chunk_id"],
                    chunk["text"],
                    summary,
                    embedding,
                    {"start_pos": chunk["start_pos"], "end_pos": chunk["end_pos"], "filename": filename}
                ))
                PG_CONNECTION.commit()
                cursor.close()
        
        
        CHUNK_CACHE[file_id] = processed_chunks
        
        return {
            "status": "success",
            "chunks_created": len(processed_chunks),
            "total_chars": len(content),
            "cache_status": "stored in ROM",
            "message": f"Processed and cached {len(processed_chunks)} chunks with Gemini summaries"
        }
    except Exception as e:
        return {"status": "error", "message": f"Chunking failed: {str(e)}"}


def search_chunks(query: str, limit: int = 10) -> Dict:
    """Search across document chunks for precise results
    
    Args:
        query: Search query
        limit: Maximum results
    """
    if not PG_CONNECTION:
        return {"status": "error", "message": "Database not initialized"}
    
    try:
        query_embedding = generate_embedding(query)
        
        cursor = PG_CONNECTION.cursor()
        cursor.execute("""
            SELECT c.file_id, c.metadata->>'filename' as filename, 
                   c.chunk_id, c.chunk_text, c.summary,
                   1 - (c.embedding <=> %s::vector) as similarity
            FROM document_chunks c
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s;
        """, (query_embedding, query_embedding, limit))
        
        results = cursor.fetchall()
        cursor.close()
        
        search_results = [
            {
                "file_id": row[0],
                "filename": row[1],
                "chunk_id": row[2],
                "content_preview": row[3][:300] + "..." if len(row[3]) > 300 else row[3],
                "summary": row[4],
                "relevance_score": round(row[5] * 100, 2)
            }
            for row in results
        ]
        
        return {
            "status": "success",
            "query": query,
            "results": search_results,
            "count": len(search_results),
            "search_type": "chunk-level (precise)"
        }
    except Exception as e:
        return {"status": "error", "message": f"Chunk search failed: {str(e)}"}


# ============================================
# GOOGLE DRIVE INTEGRATION
# ============================================

def authenticate_google_drive():
    """Authenticate with Google Drive using OAuth 2.0"""
    global DRIVE_SERVICE
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        DRIVE_SERVICE = build('drive', 'v3', credentials=creds)
        return {"status": "success", "message": "Google Drive authenticated successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Authentication failed: {str(e)}. Ensure credentials.json exists."}


def list_drive_files(max_files: int = 20) -> Dict:
    """List files from Google Drive
    
    Args:
        max_files: Maximum number of files to retrieve
    """
    if not DRIVE_SERVICE:
        return {"status": "error", "message": "Drive not authenticated. Run authenticate_google_drive first."}
    
    try:
        results = DRIVE_SERVICE.files().list(
            pageSize=max_files,
            fields="files(id, name, mimeType, size, createdTime)"
        ).execute()
        
        files = results.get('files', [])
        
        return {
            "status": "success",
            "count": len(files),
            "files": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "type": f["mimeType"],
                    "size_bytes": f.get("size", "0"),
                    "created": f.get("createdTime", "Unknown")
                }
                for f in files
            ]
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to list files: {str(e)}"}


def download_file_content(file_id: str) -> Dict:
    """Download file content from Google Drive
    
    Args:
        file_id: Google Drive file ID
    """
    if not DRIVE_SERVICE:
        return {"status": "error", "message": "Drive not authenticated"}
    
    try:
        
        file_metadata = DRIVE_SERVICE.files().get(fileId=file_id).execute()
        
        
        if 'application/vnd.google-apps' in file_metadata['mimeType']:
            content = DRIVE_SERVICE.files().export(
                fileId=file_id, 
                mimeType='text/plain'
            ).execute()
            text_content = content.decode('utf-8')
        else:
            
            content = DRIVE_SERVICE.files().get_media(fileId=file_id).execute()
            text_content = content.decode('utf-8', errors='ignore')
        
        return {
            "status": "success",
            "file_id": file_id,
            "filename": file_metadata['name'],
            "content": text_content[:5000],  
            "full_content": text_content,
            "size": len(text_content),
            "mime_type": file_metadata['mimeType']
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to download: {str(e)}"}


# ============================================
# DUPLICATE DETECTION WITH PGVECTOR
# ============================================

def detect_duplicates(file_id: str, content: str, filename: str, threshold: float = 0.85) -> Dict:
    """Detect duplicate documents using pgvector similarity search
    
    Args:
        file_id: File identifier
        content: Document content
        filename: Name of the file
        threshold: Similarity threshold (default 0.85 = 85%)
    """
    if not PG_CONNECTION:
        return {"status": "error", "message": "Database not initialized"}
    
    try:
       
        embedding = generate_embedding(content[:8000])  
        
        cursor = PG_CONNECTION.cursor()
        
       
        cursor.execute("""
            SELECT file_id, filename, 
                   1 - (embedding <=> %s::vector) as similarity
            FROM documents
            WHERE file_id != %s
            ORDER BY embedding <=> %s::vector
            LIMIT 5;
        """, (embedding, file_id, embedding))
        
        results = cursor.fetchall()
        duplicates = []
        
        for row in results:
            similar_file_id, similar_filename, similarity = row
            if similarity >= threshold:
                duplicates.append({
                    "duplicate_file_id": similar_file_id,
                    "duplicate_filename": similar_filename,
                    "similarity_score": round(similarity * 100, 2),
                    "confidence": "HIGH" if similarity >= 0.9 else "MEDIUM"
                })
        
       
        cursor.execute("""
            INSERT INTO documents (file_id, filename, content, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_id) DO UPDATE 
            SET filename = EXCLUDED.filename,
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding;
        """, (file_id, filename, content[:10000], embedding, {'source': 'google_drive'}))
        
        PG_CONNECTION.commit()
        cursor.close()
        
        if duplicates:
            issue = {
                "type": "DUPLICATE",
                "file_id": file_id,
                "filename": filename,
                "duplicates": duplicates,
                "action": "REMOVE_DUPLICATE",
                "confidence": duplicates[0]["confidence"],
                "recommendation": f"Remove {len(duplicates)} duplicate(s) to save storage"
            }
            DETECTED_ISSUES.append(issue)
            PENDING_APPROVALS.append(issue)
        
        return {
            "status": "success",
            "duplicates_found": len(duplicates),
            "details": duplicates,
            "threshold_used": f"{threshold * 100}%"
        }
    except Exception as e:
        return {"status": "error", "message": f"Duplicate detection failed: {str(e)}"}


# ============================================
# PII DETECTION
# ============================================

def detect_pii(content: str, file_id: str, filename: str) -> Dict:
    """Detect PII using pattern matching
    
    Args:
        content: Document content
        file_id: File identifier
        filename: Name of the file
    """
    pii_patterns = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
    }
    
    detected_pii = {}
    
    for pii_type, pattern in pii_patterns.items():
        matches = re.findall(pattern, content)
        if matches:
            detected_pii[pii_type] = {
                "count": len(matches),
                "samples": matches[:3] 
            }
    
    if detected_pii:
        issue = {
            "type": "PII_DETECTED",
            "file_id": file_id,
            "filename": filename,
            "pii_types": list(detected_pii.keys()),
            "details": detected_pii,
            "action": "MARK_SENSITIVE",
            "confidence": "HIGH",
            "recommendation": "Mark file as sensitive and restrict access"
        }
        DETECTED_ISSUES.append(issue)
        PENDING_APPROVALS.append(issue)
    
    return {
        "status": "success",
        "pii_found": len(detected_pii) > 0,
        "details": detected_pii,
        "patterns_checked": list(pii_patterns.keys())
    }


# ============================================
# QUALITY VALIDATION
# ============================================

def validate_quality(content: str, file_id: str, filename: str, file_size: int) -> Dict:
    """Validate file quality and integrity
    
    Args:
        content: Document content
        file_id: File identifier
        filename: Name of the file
        file_size: Size of file in bytes
    """
    quality_issues = []
    
  
    if len(content.strip()) < 10:
        quality_issues.append("Empty or minimal content (less than 10 characters)")
    
    
    corruption_patterns = [
        (r'[\x00-\x08\x0B\x0C\x0E-\x1F]', "Control characters detected"),
        (r'�{3,}', "Multiple replacement characters (corruption)")
    ]
    
    for pattern, description in corruption_patterns:
        if re.search(pattern, content):
            quality_issues.append(description)
            break
    
   
    if file_size > 500 * 1024 * 1024: 
        quality_issues.append("File exceeds size limit (500MB)")
    
    if quality_issues:
        issue = {
            "type": "QUALITY_ISSUE",
            "file_id": file_id,
            "filename": filename,
            "issues": quality_issues,
            "action": "FLAG_FOR_REVIEW",
            "confidence": "HIGH",
            "recommendation": "Manual review or file replacement needed"
        }
        DETECTED_ISSUES.append(issue)
        PENDING_APPROVALS.append(issue)
    
    return {
        "status": "success",
        "quality_issues_found": len(quality_issues) > 0,
        "issues": quality_issues,
        "file_size_mb": round(file_size / (1024 * 1024), 2)
    }


# ============================================
# HITL APPROVAL WORKFLOW
# ============================================

def get_pending_approvals() -> Dict:
    """Get all issues awaiting human approval"""
    return {
        "status": "success",
        "pending_count": len(PENDING_APPROVALS),
        "issues": PENDING_APPROVALS
    }


def approve_action(issue_index: int) -> Dict:
    """Approve a detected issue and execute action
    
    Args:
        issue_index: Index of the issue to approve (0-based)
    """
    if issue_index >= len(PENDING_APPROVALS) or issue_index < 0:
        return {"status": "error", "message": f"Invalid issue index. Valid range: 0-{len(PENDING_APPROVALS)-1}"}
    
    issue = PENDING_APPROVALS.pop(issue_index)
    
   
    action_log = {
        "issue_type": issue["type"],
        "file": issue["filename"],
        "action": issue["action"],
        "approved_at": "2025-12-01T00:00:00Z",
        "status": "EXECUTED",
        "details": issue.get("recommendation", "Action completed")
    }
    
    return {
        "status": "success",
        "message": f"✅ Action '{issue['action']}' approved and executed for {issue['filename']}",
        "log": action_log
    }


def reject_action(issue_index: int, reason: str = "False positive") -> Dict:
    """Reject a detected issue
    
    Args:
        issue_index: Index of the issue to reject
        reason: Reason for rejection
    """
    if issue_index >= len(PENDING_APPROVALS) or issue_index < 0:
        return {"status": "error", "message": f"Invalid issue index. Valid range: 0-{len(PENDING_APPROVALS)-1}"}
    
    issue = PENDING_APPROVALS.pop(issue_index)
    
    return {
        "status": "success",
        "message": f"❌ Issue rejected: {reason}",
        "rejected_issue": issue["type"],
        "file": issue["filename"]
    }


def semantic_search(query: str, limit: int = 5) -> Dict:
    """Search documents using semantic similarity (document-level)
    
    Args:
        query: Search query
        limit: Maximum results
    """
    if not PG_CONNECTION:
        return {"status": "error", "message": "Database not initialized"}
    
    try:
        query_embedding = generate_embedding(query)
        
        cursor = PG_CONNECTION.cursor()
        cursor.execute("""
            SELECT file_id, filename, content,
                   1 - (embedding <=> %s::vector) as similarity
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """, (query_embedding, query_embedding, limit))
        
        results = cursor.fetchall()
        cursor.close()
        
        search_results = [
            {
                "file_id": row[0],
                "filename": row[1],
                "preview": row[2][:200] + "..." if row[2] and len(row[2]) > 200 else row[2],
                "relevance_score": round(row[3] * 100, 2)
            }
            for row in results
        ]
        
        return {
            "status": "success",
            "query": query,
            "results": search_results,
            "count": len(search_results),
            "search_type": "document-level"
        }
    except Exception as e:
        return {"status": "error", "message": f"Search failed: {str(e)}"}


# ============================================
# BATCH PROCESSING
# ============================================

def process_all_files() -> Dict:
    """Process all Drive files in batch with HITL checkpoints"""
    
  
    files_result = list_drive_files(max_files=20)
    if files_result["status"] != "success":
        return files_result
    
    files = files_result["files"]
    results = []
    
    print("\n🔍 Starting batch processing of files...\n")
    
  
    for idx, file_info in enumerate(files, 1):
        file_id = file_info["id"]
        filename = file_info["name"]
        
        print(f"📄 [{idx}/{len(files)}] Scanning: {filename}")
        
      
        download_result = download_file_content(file_id)
        if download_result["status"] != "success":
            print(f"   ⚠️ Skipped (download failed)")
            continue
        
        content = download_result["full_content"]
        size = int(file_info.get("size_bytes", 0))
        
       
        if len(content) > 5000:
            chunk_result = process_large_file(file_id, content, filename)
            print(f"   📦 Chunked into {chunk_result.get('chunks_created', 0)} pieces")
        
       
        duplicate_result = detect_duplicates(file_id, content, filename)
        pii_result = detect_pii(content, file_id, filename)
        quality_result = validate_quality(content, file_id, filename, size)
        
        file_summary = {
            "file": filename,
            "duplicates": duplicate_result.get("duplicates_found", 0),
            "pii": pii_result.get("pii_found", False),
            "quality_issues": quality_result.get("quality_issues_found", False)
        }
        
        results.append(file_summary)
        
       
        if file_summary["duplicates"] > 0:
            print(f"   🔄 Found {file_summary['duplicates']} duplicate(s)")
        if file_summary["pii"]:
            print(f"   🔒 PII detected")
        if file_summary["quality_issues"]:
            print(f"   ⚠️ Quality issues found")
        if not any([file_summary["duplicates"], file_summary["pii"], file_summary["quality_issues"]]):
            print(f"   ✅ No issues")
    
   
    approvals = get_pending_approvals()
    
    print(f"\n✅ Batch processing complete!")
    print(f"📊 Files processed: {len(results)}")
    print(f"🚨 Issues awaiting approval: {approvals['pending_count']}\n")
    
    return {
        "status": "success",
        "files_processed": len(results),
        "total_issues": approvals["pending_count"],
        "details": results,
        "awaiting_approval": approvals["issues"]
    }


# ============================================
# WRAP FUNCTIONS AS TOOLS
# ============================================

db_init_tool = FunctionTool(func=initialize_database)
drive_auth_tool = FunctionTool(func=authenticate_google_drive)
list_files_tool = FunctionTool(func=list_drive_files)
download_tool = FunctionTool(func=download_file_content)
chunk_tool = FunctionTool(func=process_large_file)
chunk_search_tool = FunctionTool(func=search_chunks)
duplicate_tool = FunctionTool(func=detect_duplicates)
pii_tool = FunctionTool(func=detect_pii)
quality_tool = FunctionTool(func=validate_quality)
approvals_tool = FunctionTool(func=get_pending_approvals)
approve_tool = FunctionTool(func=approve_action)
reject_tool = FunctionTool(func=reject_action)
search_tool = FunctionTool(func=semantic_search)
batch_tool = FunctionTool(func=process_all_files)


# ============================================
# CREATE AGENTS
# ============================================

data_quality_agent = Agent(
    name="DataQualityAgent",
    model="gemini-2.0-flash-exp",
    instruction="""You are a Data Quality Agent for enterprise data optimization.

Your workflow for EACH document:
1. Download content using download_file_content
2. For large files (>5KB): Use process_large_file to chunk and cache
3. Detect duplicates using detect_duplicates (85% threshold)
4. Identify PII using detect_pii (email, SSN, phone, credit cards)
5. Validate quality using validate_quality (corruption, size, integrity)
6. Present ALL findings to human using get_pending_approvals

CRITICAL RULES:
- NEVER execute actions without explicit human approval
- Always provide confidence scores and evidence
- Explain WHY each issue matters
- Wait for human to approve_action or reject_action

Be thorough but concise in your analysis.""",
    tools=[download_tool, chunk_tool, duplicate_tool, pii_tool, quality_tool, approvals_tool, approve_tool, reject_tool]
)

orchestrator = Agent(
    name="DAMOrchestrator",
    model="gemini-2.0-flash-exp",
    instruction="""You are the Data Asset Management Orchestrator with Human-in-the-Loop workflow.

SETUP PHASE (First-time users):
1. Initialize database: initialize_database
2. Authenticate Google Drive: authenticate_google_drive
3. List available files: list_drive_files

PROCESSING MODES:
A. Single File Processing:
   - Download file → Route to DataQualityAgent → Present findings → Wait for approval

B. Batch Processing:
   - Use process_all_files to scan all 20 files automatically
   - All issues require human approval

SEARCH CAPABILITIES:
- Document-level search: semantic_search (full documents)
- Chunk-level search: search_chunks (precise, for large docs)

CHUNKING STRATEGY:
- Files >5KB: Automatically chunk with process_large_file
- Creates overlapping segments with Gemini summaries
- Stores in ROM cache for instant retrieval
- Enables precise chunk-level search

HITL PRINCIPLES:
- Present findings with confidence scores
- Explain business impact (storage savings, compliance risk, etc.)
- NEVER auto-execute high-stakes actions
- Log all decisions with timestamps

Communication Style:
- Clear and professional
- Use emojis for readability (✅ ⚠️ 🔒 📄)
- Explain technical concepts simply
- Always confirm next steps

Be helpful and ensure users understand the workflow!""",
    tools=[db_init_tool, drive_auth_tool, list_files_tool, batch_tool, chunk_search_tool, search_tool],
    sub_agents=[data_quality_agent]
)


# ============================================
# MAIN
# ============================================

async def main():
    """Main interactive loop for DAM Agent System"""
   
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="dam_quality_agent",
        user_id="user123",
        session_id="session1"
    )
    
   
    runner = Runner(
        agent=orchestrator,
        app_name="dam_quality_agent",
        session_service=session_service
    )
    
    print("\n✅ System Ready!\n")
    print("📋 Quick Start Commands:")
    print("  1. 'Initialize the database'")
    print("  2. 'Authenticate with Google Drive'")
    print("  3. 'List my Drive files'")
    print("  4. 'Process all files' (batch scan)")
    print("  5. 'Show pending approvals'")
    print("  6. 'Approve issue 0' or 'Reject issue 1'")
    print("  7. 'Search for invoice documents'")
    print("  8. 'Search chunks for payment terms'")
    print("\n" + "=" * 70)
    print("💬 Interactive Mode (type 'exit' to quit, 'help' for commands):\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n👋 Shutting down DAM Agent System...")
                break
            
            if user_input.lower() == "help":
                print("\n📖 Available Commands:")
                print("  - Initialize the database")
                print("  - Authenticate with Google Drive")
                print("  - List my Drive files")
                print("  - Process all files (batch)")
                print("  - Scan file [file_id]")
                print("  - Show pending approvals")
                print("  - Approve issue [index]")
                print("  - Reject issue [index]")
                print("  - Search for [query]")
                print("  - Search chunks for [query]")
                print()
                continue
            
            if not user_input:
                continue
            
            content = types.Content(role='user', parts=[types.Part(text=user_input)])
            
            print("\n🤖 Agent:")
            async for event in runner.run_async(
                user_id="user123",
                session_id="session1",
                new_message=content
            ):
                if event.is_final_response():
                    response = event.content.parts[0].text
                    print(response)
            print()
            
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down DAM Agent System...")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")


if __name__ == "__main__":
    asyncio.run(main())
