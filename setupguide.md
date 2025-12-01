# Setup Guide - Data Asset Management Agent

Complete step-by-step instructions to set up and run the DAM Agent system.

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Installation Steps](#installation-steps)
3. [Configuration](#configuration)
4. [First Run](#first-run)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Configuration](#advanced-configuration)

---

## System Requirements

### Hardware
- **CPU:** 2+ cores recommended (4+ for better performance)
- **RAM:** 8GB minimum, 16GB recommended
- **Storage:** 10GB free space (for PostgreSQL + Ollama models)

### Software
- **OS:** macOS 11+, Ubuntu 20.04+, or Windows 10/11
- **Python:** 3.11 or higher
- **PostgreSQL:** 14 or higher
- **Ollama:** Latest version
- **Git:** For cloning repository

### Cloud Services
- **Google Drive** account with test files
- **Google Cloud Platform** project (free tier)
- **Gemini API** key (free tier available)

---

## Installation Steps

### Step 1: Install System Dependencies

#### macOS
```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install PostgreSQL 14
brew install postgresql@14

# Install pgvector extension
brew install pgvector

# Install Ollama
brew install ollama

# Start PostgreSQL service
brew services start postgresql@14

# Verify PostgreSQL is running
brew services list | grep postgresql
```

#### Ubuntu/Debian Linux
```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Install build dependencies for pgvector
sudo apt install postgresql-server-dev-14 build-essential

# Install pgvector
cd /tmp
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify PostgreSQL
sudo systemctl status postgresql
```

#### Windows
```powershell
# Install PostgreSQL
# Download from: https://www.postgresql.org/download/windows/
# Run installer and follow prompts

# Install pgvector
# Follow instructions: https://github.com/pgvector/pgvector#windows

# Install Ollama
# Download from: https://ollama.com/download/windows
# Run installer

# Verify installations
pg_config --version
ollama --version
```

---

### Step 2: Setup PostgreSQL Database

#### Create Database

```bash
# macOS/Linux
createdb dam_agent

# Windows (in psql)
psql -U postgres
CREATE DATABASE dam_agent;
\q
```

#### Set PostgreSQL Password (if needed)

```bash
# macOS/Linux
psql postgres
\password postgres
# Enter password: postgres
\q

# Windows
# Use pgAdmin or psql to set password
```

#### Test Connection

```bash
psql -d dam_agent -c "SELECT version();"

# Expected output:
# PostgreSQL 14.x on x86_64-...
```

---

### Step 3: Install Ollama Model

```bash
# Start Ollama service (if not running)
# macOS/Linux
ollama serve &

# Windows: Ollama runs as a service automatically

# Pull nomic-embed-text model (768-dimensional embeddings)
ollama pull nomic-embed-text

# Verify model is downloaded
ollama list

# Expected output:
# NAME                    SIZE    MODIFIED
# nomic-embed-text:latest 274MB   X minutes ago

# Test embedding generation
ollama embeddings --model nomic-embed-text --prompt "test"
```

---

### Step 4: Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/DAM-Agent-ADK.git

# Navigate to project directory
cd DAM-Agent-ADK

# Verify files
ls -la

# Expected files:
# agent.py, requirements.txt, README.md, setup_guide.md, etc.
```

---

### Step 5: Python Environment Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate

# Windows (PowerShell):
venv\Scripts\Activate.ps1

# Windows (Command Prompt):
venv\Scripts\activate.bat

# Verify activation (should show venv path)
which python  # macOS/Linux
where python  # Windows

# Upgrade pip
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt

# Verify installations
pip list | grep -E "google-adk|ollama|psycopg2|pgvector"
```

#### Troubleshooting Installation

If you encounter errors:

```bash
# Error: "No module named 'google.adk'"
pip install --upgrade google-adk

# Error: "psycopg2 installation failed"
# Try binary version:
pip uninstall psycopg2
pip install psycopg2-binary

# Error: "pgvector not found"
pip install --no-cache-dir pgvector

# Nuclear option: Reinstall everything
pip uninstall -r requirements.txt -y
pip install -r requirements.txt --no-cache-dir
```

---

### Step 6: Setup Google Cloud APIs

#### A. Get Gemini API Key (FREE)

1. Visit [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **"Create API Key"**
3. Copy your API key (starts with `AIza...`)
4. Save securely - you'll need it in Step 7

#### B. Setup Google Drive OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. **Create Project:**
   - Click "Select a project" → "New Project"
   - Name: `DAM-Agent`
   - Click "Create"

3. **Enable Google Drive API:**
   - Navigate to **"APIs & Services" → "Library"**
   - Search for: `Google Drive API`
   - Click on it → Click **"Enable"**
   - Wait for activation (30 seconds)

4. **Create OAuth 2.0 Credentials:**
   - Go to **"APIs & Services" → "Credentials"**
   - Click **"Create Credentials" → "OAuth client ID"**
   - If prompted, configure consent screen:
     - User Type: **External**
     - App name: `DAM Agent`
     - User support email: Your email
     - Developer contact: Your email
     - Click **"Save and Continue"** through all steps

   - Return to Create OAuth client ID:
     - Application type: **"Desktop app"**
     - Name: `DAM Agent Desktop`
     - Click **"Create"**

5. **Download Credentials:**
   - Click the download icon (⬇️) next to your OAuth client
   - Save file as `credentials.json`
   - **Move to project root directory:**
     ```bash
     mv ~/Downloads/client_secret_*.json ./credentials.json
     ```

---

## Configuration

### Step 7: Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example template
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor
```

**Add the following configuration:**

```bash
# Gemini API Key (from Google AI Studio)
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# PostgreSQL Configuration
PG_DATABASE=dam_agent
PG_USER=postgres
PG_PASSWORD=postgres
PG_HOST=localhost
PG_PORT=5432

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
```

**Load environment variables:**

```bash
# macOS/Linux
export $(cat .env | xargs)

# Or add to shell profile
echo 'export GOOGLE_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc

# Windows (PowerShell)
Get-Content .env | ForEach-Object {
    $name, $value = $_.split('=')
    [Environment]::SetEnvironmentVariable($name, $value, 'User')
}
```

---

### Step 8: Initialize Database Schema

Run the setup script:

```bash
chmod +x setup_postgres.sh
./setup_postgres.sh
```

**Or manually execute SQL:**

```bash
psql -d dam_agent << 'EOF'
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL,
    filename VARCHAR(500) NOT NULL,
    content TEXT,
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create document_chunks table
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

-- Create vector indexes
CREATE INDEX IF NOT EXISTS documents_embedding_idx 
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Verify tables created
\dt
EOF
```

**Verify tables exist:**

```bash
psql -d dam_agent -c "\dt"

# Expected output:
#              List of relations
#  Schema |       Name        | Type  |  Owner
# --------+-------------------+-------+----------
#  public | document_chunks   | table | postgres
#  public | documents         | table | postgres
```

---

### Step 9: Prepare Test Data

#### Create Google Drive Folder

1. Go to [Google Drive](https://drive.google.com/)
2. Create a new folder: `DAM Agent Test Files`
3. Upload 20 sample documents:

**Recommended Structure:**

**Invoices (6 files - 3 duplicate pairs):**
- `invoice_001.pdf` (original)
- `invoice_001_copy.pdf` (duplicate)
- `invoice_002.pdf` (original)
- `invoice_002_duplicate.pdf` (duplicate)
- `invoice_003.pdf` (original)
- `invoice_003_v2.pdf` (duplicate)

**Customer Records (4 files with synthetic PII):**
- `customer_records_jan.docx`
  ```
  Customer: John Doe
  Email: john.doe@example.com
  Phone: 555-123-4567
  SSN: 123-45-6789
  ```
- `customer_records_feb.docx`
- `customer_records_mar.docx`
- `customer_records_q1.xlsx`

**Sales Reports (5 files):**
- `sales_report_q1_2024.pdf`
- `sales_report_q2_2024.pdf`
- `sales_summary_2024.xlsx`
- `revenue_analysis.docx`
- `forecast_2025.pdf`

**Internal Memos (3 files):**
- `team_meeting_notes.docx`
- `project_update.pdf`
- `policy_changes.docx`

**Corrupted Files (2 files - intentionally broken):**
- Create a text file, add random characters: `��� corrupted���`
- Save as `corrupted_file_1.txt`
- Repeat for `corrupted_file_2.txt`

---

## First Run

### Step 10: Launch the Agent

```bash
# Ensure all services are running
ollama serve &                     # Start Ollama
brew services start postgresql@14  # Start PostgreSQL (macOS)

# Activate virtual environment
source venv/bin/activate

# Run the agent
python agent.py
```

### Step 11: Initial Authentication

**First-time run sequence:**

```
You: Initialize the database

Agent: 🔧 Initializing PostgreSQL + pgvector...
       ✅ PostgreSQL + pgvector initialized with chunking support

You: Authenticate with Google Drive

Agent: 🌐 Opening browser for OAuth authentication...
```

- Browser will open automatically
- Select your Google account
- Click **"Allow"** to grant Drive read-only access
- Return to terminal

```
Agent: ✅ Google Drive authenticated successfully
```

### Step 12: Test Basic Workflow

```
You: List my Drive files

Agent: 📂 Found 20 files:
  1. invoice_001.pdf (2.5MB)
  2. invoice_001_copy.pdf (2.5MB)
  3. customer_records_jan.docx (45KB)
  ...

You: Process all files

Agent: 🔍 Starting batch processing of files...

📄 [1/20] Scanning: invoice_001.pdf
   📦 Chunked into 8 pieces
   ✅ No issues

📄 [2/20] Scanning: invoice_001_copy.pdf
   🔄 Found 1 duplicate (92% similarity)

📄 [3/20] Scanning: customer_records_jan.docx
   🔒 PII detected (1 email, 1 phone, 1 SSN)

[... continues for all files ...]

✅ Batch processing complete!
📊 Files processed: 20
🚨 Issues awaiting approval: 8

You: Show pending approvals

Agent: 8 issues require your decision:
  [0] DUPLICATE - invoice_001_copy.pdf (HIGH, 92% match)
  [1] DUPLICATE - invoice_002_duplicate.pdf (HIGH, 89% match)
  [2] PII_DETECTED - customer_records_jan.docx
  [3] PII_DETECTED - customer_records_feb.docx
  ...

You: Approve issue 0

Agent: ✅ Action 'REMOVE_DUPLICATE' approved and executed
       📊 Storage saved: 2.5MB
```

---

## Troubleshooting

### Common Issues

#### 1. **"Database connection failed"**

```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# If stopped, start it:
brew services start postgresql@14

# Test connection
psql -d dam_agent -c "SELECT 1;"
```

#### 2. **"Ollama connection refused"**

```bash
# Check Ollama process
ps aux | grep ollama

# If not running, start it:
ollama serve &

# Wait 5 seconds, then test
curl http://localhost:11434/api/tags
```

#### 3. **"Google Drive authentication failed"**

```bash
# Verify credentials.json exists
ls -la credentials.json

# If missing, re-download from Google Cloud Console

# Check file permissions
chmod 644 credentials.json
```

#### 4. **"ImportError: No module named 'google.adk'"**

```bash
# Activate venv first
source venv/bin/activate

# Reinstall dependencies
pip install --upgrade google-adk google-generativeai
```

#### 5. **"Vector dimension mismatch"**

```bash
# Ensure nomic-embed-text is pulled
ollama pull nomic-embed-text

# Verify model
ollama list

# Clear database and reinitialize
psql -d dam_agent -c "DROP TABLE IF EXISTS documents CASCADE;"
psql -d dam_agent -c "DROP TABLE IF EXISTS document_chunks CASCADE;"
./setup_postgres.sh
```

#### 6. **"API key invalid"**

```bash
# Check environment variable
echo $GOOGLE_API_KEY

# If empty, reload .env
export $(cat .env | xargs)

# Test API key
curl -H "Content-Type: application/json" \
     -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
     "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GOOGLE_API_KEY"
```

---

## Advanced Configuration

### Performance Tuning

#### PostgreSQL Optimization

Edit `/usr/local/var/postgresql@14/postgresql.conf` (macOS) or `/etc/postgresql/14/main/postgresql.conf` (Linux):

```ini
# Increase memory for better performance
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 128MB

# Optimize for vector search
max_parallel_workers_per_gather = 4
```

Restart PostgreSQL:
```bash
brew services restart postgresql@14
```

#### Ollama Performance

```bash
# Use GPU acceleration (if available)
# macOS M1/M2/M3:
ollama serve  # Automatically uses Metal

# Linux with NVIDIA GPU:
OLLAMA_GPU=1 ollama serve

# Adjust concurrent requests
OLLAMA_NUM_PARALLEL=4 ollama serve
```

### Security Hardening

#### 1. **Encrypt credentials.json**

```bash
# Encrypt with GPG
gpg -c credentials.json

# Store encrypted version
mv credentials.json.gpg ~/secure/

# Decrypt when needed
gpg -d ~/secure/credentials.json.gpg > ./credentials.json
```

#### 2. **Use environment-specific configs**

```bash
# Development
cp .env .env.development

# Production
cp .env .env.production

# Load based on environment
export ENV=production
export $(cat .env.$ENV | xargs)
```

#### 3. **Rotate API keys regularly**

```bash
# Create new Gemini API key quarterly
# Update .env with new key
# Revoke old key in Google AI Studio
```

### Docker Deployment (Optional)

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "agent.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg14
    environment:
      POSTGRES_DB: dam_agent
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  agent:
    build: .
    depends_on:
      - postgres
      - ollama
    environment:
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      PG_HOST: postgres
      OLLAMA_HOST: http://ollama:11434
    volumes:
      - ./credentials.json:/app/credentials.json

volumes:
  pgdata:
  ollama_data:
```

---

## Health Checks

### System Health Dashboard

```bash
# Run comprehensive health check
python << 'EOF'
import psycopg2
import ollama
import os

print("🏥 DAM Agent Health Check\n")

# 1. PostgreSQL
try:
    conn = psycopg2.connect("dbname=dam_agent user=postgres")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents;")
    doc_count = cur.fetchone()[0]
    print(f"✅ PostgreSQL: Connected ({doc_count} documents)")
    conn.close()
except Exception as e:
    print(f"❌ PostgreSQL: {e}")

# 2. Ollama
try:
    models = ollama.list()
    if any('nomic-embed-text' in m['name'] for m in models['models']):
        print("✅ Ollama: nomic-embed-text ready")
    else:
        print("⚠️  Ollama: nomic-embed-text not found")
except Exception as e:
    print(f"❌ Ollama: {e}")

# 3. API Key
if os.getenv('GOOGLE_API_KEY'):
    print("✅ Gemini API Key: Configured")
else:
    print("❌ Gemini API Key: Missing")

# 4. Credentials
if os.path.exists('credentials.json'):
    print("✅ Google Drive OAuth: credentials.json found")
else:
    print("❌ Google Drive OAuth: credentials.json missing")

print("\n✅ Health check complete!")
EOF
```

---

## Next Steps

1. ✅ **System configured** - All services running
2. ✅ **Test data uploaded** - 20 files in Google Drive
3. ✅ **Agent tested** - Batch processing works
4. 📝 **Document your setup** - Take screenshots for writeup
5. 🚀 **Push to GitHub** - Commit all code
6. 📋 **Submit to Kaggle** - Write competition submission

---

## Support & Resources

- **Issues:** [GitHub Issues](https://github.com/yourusername/DAM-Agent-ADK/issues)
- **Documentation:** [README.md](README.md)
- **Kaggle:** [Competition Page](https://www.kaggle.com/competitions/agents-intensive-capstone-project)

---

**Setup complete! You're ready to optimize your data assets! 🎉**
