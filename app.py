# app.py
import os
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import UnstructuredPDFLoader
import markdown2
from model import ChatMessage, db
import re
import requests

from populate_database import PDFChromaIngestor


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
socketio = SocketIO(app, async_mode='threading')

# Configuration de SQLAlchemy avec SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Création des tables
with app.app_context():
    db.create_all()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

CHROMA_PATH = "chroma_langchain_db"

PROMPT_TEMPLATE = """
You are a knowledgeable and articulate assistant. 
Based solely on the context provided below, produce a detailed and self-contained answer to the question. 
Structure your answer with clear sections, such as:

1. **Overview:** A brief summary or introduction.
2. **Key Details:** Explanation of the relevant facts or technical points.
3. **Insights or Comparisons:** Any additional analysis, recommendations, or comparisons that help clarify the answer.

Do not refer to internal labels or figures from the context. Ensure your answer is easy to understand on its own.

Conversation So Far:
{chat_history}

Retrieved Context:
{context}

Question:
{question}

Answer:
"""


prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)

#########################
#    LLM & Embedding    #
#########################
ingestor = PDFChromaIngestor()
db_chroma = ingestor.db

def get_available_models():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags")  # Default Ollama API endpoint
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data['models'] \
                      if 'all-minilm' not in model['name'] and 'embed'not in model['name']]
            return models
        else:
            return ["llama3.2"]  # Fallback to default model if API fails
    except Exception as e:
        print(f"Error fetching models: {e}")
        return ["llama3.2"]  # Fallback in case of errors

###########################
#    Routes principales   #
###########################

@app.route("/", methods=["GET", "POST"])
def index():
    # Récupérer le chat courant depuis la session (si non défini, on le crée par défaut)
    available_models = get_available_models()
    selected_model = session.get('selected_model', 'llama3.2')  # Default to 'llama3.2' if not set
    current_chat = session.get("current_chat", "chat_1")
    session["current_chat"] = current_chat

    # Récupérer l'historique du chat courant depuis la BDD
    conversation = ChatMessage.query.filter_by(chat_id=current_chat).order_by(ChatMessage.timestamp).all()

    # Récupérer la liste de tous les chat_id distincts pour la barre latérale
    distinct_chats = [row[0] for row in db.session.query(ChatMessage.chat_id).distinct().all()]
    chats = {chat_id: [] for chat_id in distinct_chats}

    return render_template("index.html",
                           conversation=conversation,
                           current_chat=current_chat,
                           chats=chats,
                           available_models=available_models,
                           selected_model=selected_model)

@app.route('/reset_chroma', methods=['POST'])
def reset_chroma():
    try:
        ingestor.reset_db()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

############################
#   SOCKET.IO UPDATES      #
############################

@socketio.on('update_chroma')
def handle_update_chroma_event():
    """
    Ingests PDF chunks into Chroma one by one, emitting progress.
    """
    seen_path = ingestor.get_indexed_pdf_paths()
    new_paths  = [p for p in ingestor.data_paths if p not in seen_path]

    total_files = len(new_paths)

    if total_files == 0:
        emit('update_complete', {'added': 0}, room=request.sid)
        return

    docs = []
    for idx, path in enumerate(new_paths):    
        emit(
            'loading_progress', {
                'current': idx+1,
                'total': total_files
            }, room=request.sid
        )
        socketio.sleep(0)
        document_loader = UnstructuredPDFLoader(path)
        doc = document_loader.load()
        docs.extend(doc)

    chunks = ingestor.split_documents(docs)

    emit('update_progress', room=request.sid)
    socketio.sleep(0)
    ingestor.add_to_chroma(chunks)
    emit('update_complete', {'added': len(new_paths)}, room=request.sid)

@app.route("/new_chat", methods=["GET"])
def new_chat():
    # Récupérer la liste des chats existants
    distinct_chats = [row[0] for row in db.session.query(ChatMessage.chat_id).distinct().all()]
    new_chat_id = f"chat_{len(distinct_chats) + 1}"
    session["current_chat"] = new_chat_id
    session.modified = True
    return redirect(url_for('index'))

@app.route("/select_chat/<chat_id>", methods=["GET"])
def select_chat(chat_id):
    # Vérifier que ce chat existe dans la BDD (ou le créer)
    exists = ChatMessage.query.filter_by(chat_id=chat_id).first()
    if not exists:
        # Si le chat n'existe pas, on peut créer un nouveau chat vide
        welcome_msg = ChatMessage(chat_id=chat_id, role="assistant", content="Nouveau chat créé.")
        db.session.add(welcome_msg)
        db.session.commit()
    session["current_chat"] = chat_id
    session.modified = True
    return redirect(url_for('index'))

@app.route("/clear")
def clear_conversation():
    current_chat = session.get("current_chat", "chat_1")
    ChatMessage.query.filter_by(chat_id=current_chat).delete()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/select_model', methods=['POST'])
def select_model():
    data = request.get_json()
    model = data['model']
    session['selected_model'] = model
    session.modified = True
    return jsonify({'status': 'success', 'model': model})

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('join_chat')
def handle_join_chat(data):
    chat_id = data['chat_id']
    join_room(chat_id)
    print(f'Client joined chat {chat_id}')

@socketio.on('submit_query')
def handle_submit_query(data):
    query = data['query']
    chat_id = data['chat_id']

    selected_model = data.get('model', session.get('selected_model', 'llama3.2'))

    model = ChatOllama(model=selected_model, base_url=OLLAMA_URL)  
    # Save user message to database
    user_msg = ChatMessage(chat_id=chat_id, role="user", content=query)
    db.session.add(user_msg)
    db.session.commit()

    # Create a placeholder assistant message
    assistant_msg = ChatMessage(chat_id=chat_id, role="assistant", content="Generating...")
    db.session.add(assistant_msg)
    db.session.commit()

    # Emit the message ID to start streaming
    emit('start_stream', {'message_id': assistant_msg.id}, room=chat_id)
    
    # Retrieve documents and create prompt
    results = db_chroma.similarity_search_with_score(query, k=10)

    docs_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results if _score < 1.0]) or "No relevant documents found."

    history = (ChatMessage.query\
                .filter_by(chat_id=chat_id)\
                .order_by(ChatMessage.timestamp)\
                .all()[-10:])
    
    history_text = "\n".join(f"{m.role.title()}: {m.content}" for m in history)

    prompt = prompt_template.format(chat_history=history_text, context=docs_text, question=query)

    response_text = ""
    for chunk in model.stream(prompt):
        token = chunk.content
        response_text += token
        emit('stream_token', {'token': token, 'message_id': assistant_msg.id}, room=chat_id)
    
    # After streaming, save complete response to database
    sources = [doc.metadata.get("id", None) for doc, _score in results if _score < 1.0]
    formatted_sources = ''
    for source in sources:
        if source:
            split_string = re.split(r'[\\:]', source)
            if len(split_string) > 1:
                if split_string[-3] not in formatted_sources: 
                    formatted_sources += f"<li>{split_string[-3]}</li>\n"
    formatted_response = f"{response_text}\n\n<h4>Here my Sources:</h4>\n<ul>{formatted_sources}</ul>" if formatted_sources else response_text
    response_html = markdown2.markdown(formatted_response, extras=["fenced-code-blocks", "code-friendly", "tables"])
    # Update the assistant message with the final response
    assistant_msg.content = response_html
    db.session.commit()
    
    # Emit the final response with the message ID
    emit('final_response', {'final_message': response_html, 'message_id': assistant_msg.id}, room=chat_id)

if __name__ == "__main__":
    socketio.run(app, debug=True)
