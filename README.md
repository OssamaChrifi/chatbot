# RAG PDF QnA with Ollama & LangChain

This project is  a **local Retrieval-Augmented Generation (RAG) chatbot** built with:

- [Flask](https://flask.palletsprojects.com/) + [Flask-SocketIO](https://flask-socketio.readthedocs.io/) (web app & real-time chat)  
- [LangChain](https://www.langchain.com/) for orchestration  
- [Ollama](https://ollama.com/) for running LLMs locally (e.g., ```llama3.2```, ```mistral```, ```qwen2.5```)  
- [ChromaDB](https://www.trychroma.com/) for vector storage  
- [Docker](https://www.docker.com/) for reproducible deployment  

It allows you to **upload PDFs**, embed them locally, and query them using your chosen LLM via a **chat interface**.

---

## Features
- **Fully local**: No external API calls, all embeddings & LLM inference happen on your machine.  
- **PDF ingestion**: Extracts and splits documents with ```langchain_community``` loaders.  
- **Vector search**: Stores and retrieves chunks with ChromaDB.  
- **Realtime chat**: Built with Flask-SocketIO for interactive responses.  
- **Multi-model support**: Dynamically switch between Ollama models.  
- **Dockerized**: Simple deployment and persistence with bind mounts & volumes.  

---

## Project Structure
```
├── app.py                   # Flask web app
├── populate_database.py     # Script to ingest PDFs into Chroma
├── model.py                 # SQLAlchemy chat history model
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Service orchestration (app + Ollama)
├── templates/               # HTML templates
├── static/                  # Frontend assets (CSS/JS)
├── data/                    # PDF storage (bind-mounted)
├── chroma_langchain_db/     # ChromaDB persistence (bind-mounted)
├── instance/                # SQLite DB persistence (bind-mounted)
└── .env                     # Environment variables
```

---

## Setup

### Option 1: Run with Docker (recommended)

#### 1. Clone the repository
```
git clone <your-repo>
cd <your-repo>
```

#### 2. Configure environment
Create a ```.env``` file:
```
FLASK_SECRET_KEY=your_secret_key
OLLAMA_BASE_URL=http://ollama:11434
```

#### 3. Start services
```
docker compose up --build
```

This will:
- Start ```ollama_server``` on port **11434**
- Start ```rag_pdf_qna_app``` on port **5000**
- Mount your local ```data/```, ```chroma_langchain_db/```, and ```instance/```

#### 4. Access the app
Open [http://localhost:5000](http://localhost:5000) in your browser.

---

### Option 2: Run locally (without Docker)

#### 1. Install dependencies
Make sure [Ollama](https://ollama.com/download) is installed and running locally.  
Then set up Python environment:
```
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configure environment
Create a ```.env``` file:
```
FLASK_SECRET_KEY=your_secret_key
OLLAMA_BASE_URL=http://localhost:11434
```

#### 3. Populate database
Put your PDFs into the ```data/``` folder and run:
```
python populate_database.py
```

#### 4. Start the app
```
flask run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## Adding Documents
1. Place your PDFs inside the ```data/``` folder.  
2. Ingest them into Chroma:
   ```
   docker exec -it rag_pdf_qna_app python populate_database.py
   ```
3. Optionally reset the database:
   ```
   docker exec -it rag_pdf_qna_app python populate_database.py --reset
   ```

(If running locally, replace ```docker exec ...``` with ```python populate_database.py```.)

---

## GPU Acceleration
By default, Ollama will **use GPU if available**.  

---

## Debugging

- **Logs**:
  ```
  docker logs -f rag_pdf_qna_app
  docker logs -f ollama_server
  ```

- **Test Chroma ingestion**:
  ```
  docker exec -it rag_pdf_qna_app python populate_database.py
  ```

- **Test Ollama API**:
  ```
  docker exec -it rag_pdf_qna_app curl http://ollama:11434/api/tags
  ```

---

## Known Issues
- First query after starting a model can be slow (model load time).  
- Without GPU, inference will be slower (CPU only).  
- On Mac/Windows (Docker Desktop), GPU passthrough may not be supported.  

