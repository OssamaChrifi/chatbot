import argparse
import os
import stat
import errno
from glob import glob
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema.document import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHROMA_PATH = "chroma_langchain_db"
DATA_GLOB = "data/*.pdf"


class PDFChromaIngestor:
    def __init__(
        self,
        data_glob: str = DATA_GLOB,
        chroma_path: str = CHROMA_PATH,
        ollama_url: str = OLLAMA_URL,
        collection_name: str = "chunks_pdf",
        chunk_size: int = 1800,
        chunk_overlap: int = 200,
        embedding_model: str = "nomic-embed-text",
    ):
        self.data_glob = data_glob
        self.db = Chroma(
            collection_name=collection_name,
            persist_directory=chroma_path,
            embedding_function=OllamaEmbeddings(model=embedding_model, base_url=ollama_url),
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            add_start_index=True,
        )

    def reset_db(self):
        """Delete the existing collection directory."""
        try:
            self.db.reset_collection()
            print("✅ Database reset successfully.")
        except Exception as e:
            print(f"⚠️ Failed to reset database: {e}")

    def load_documents(self) -> list[Document]:
        """Load all PDFs via UnstructuredPDFLoader."""
        docs: list[Document] = []
        for path in self.data_paths:
            loader = UnstructuredPDFLoader(path)
            loaded = loader.load()
            docs.extend(loaded)
        print(f"📄 Loaded {len(docs)} documents from {len(self.data_paths)} files.")
        return docs

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """Split documents into overlapping chunks."""
        chunks = self.text_splitter.split_documents(documents)
        print(f"✂️ Split into {len(chunks)} chunks.")
        return chunks

    def calculate_chunk_ids(self, chunks: list[Document]) -> list[Document]:
        """Assign a unique ID to each chunk based on source, page/start_index, and ordering."""
        last_identifier = None
        current_idx = 0

        for chunk in chunks:
            source = chunk.metadata.get("source", "unknown")
            if "page" in chunk.metadata:
                identifier = chunk.metadata["page"]
            elif "start_index" in chunk.metadata:
                identifier = chunk.metadata["start_index"]
            else:
                identifier = "unknown"

            current_identifier = f"{source}:{identifier}"
            if current_identifier == last_identifier:
                current_idx += 1
            else:
                current_idx = 0

            chunk_id = f"{current_identifier}:{current_idx}"
            chunk.metadata["id"] = chunk_id
            last_identifier = current_identifier

        return chunks

    def add_to_chroma(self, chunks: list[Document]):
        """Add new chunks to the Chroma DB, skipping those already present."""
        chunks = self.calculate_chunk_ids(chunks)
        existing = self.db.get(include=[])
        existing_ids = set(existing["ids"])
        print(f"🗂️ Existing documents in DB: {len(existing_ids)}")

        new_chunks = [c for c in chunks if c.metadata["id"] not in existing_ids]
        if new_chunks:
            print(f"👉 Adding {len(new_chunks)} new chunks...")
            ids = [c.metadata["id"] for c in new_chunks]
            self.db.add_documents(new_chunks, ids=ids)
        else:
            print("✅ No new documents to add.")

    def get_indexed_pdf_paths(self)-> set[str]:
        result = self.db.get(include=[])
        indexed_id = set(result['ids'])
        return {id_str.split(':',1)[0] for id_str in indexed_id}

    @property
    def data_paths(self)-> list[str]:
        return glob(DATA_GLOB)

    @staticmethod
    def handle_remove_readonly(func, path, exc_info):
        """Helper for shutil.rmtree on Windows readonly files."""
        exc_value = exc_info[1]
        if func in (os.rmdir, os.remove, os.unlink) and exc_value.errno == errno.EACCES:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        else:
            raise

    def run(self, reset: bool = False):
        """Main execution: optionally reset DB, then load, split, and ingest."""
        if reset:
            self.reset_db()

        docs = self.load_documents()
        chunks = self.split_documents(docs)
        self.add_to_chroma(chunks)


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest PDFs into Chroma DB")
    parser.add_argument(
        "--reset", "-r", action="store_true", help="Reset (clear) the existing Chroma collection"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ingestor = PDFChromaIngestor()
    ingestor.run(reset=args.reset)
