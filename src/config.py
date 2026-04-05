from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    chroma_path: str = "./data/chroma"
    storage_path: str = "./data/uploads"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_model: str = "gpt-5.4"
    openai_api_key: str = ""
    bge_query_prefix: str = ""
    chunk_max_chars: int = 800
    chunk_target_chars: int = 600
    chunk_overlap: int = 100

    class Config:
        env_file = ".env"


settings = Settings()
