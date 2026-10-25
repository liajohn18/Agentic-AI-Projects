from pathlib import Path

from langchain_ollama import ChatOllama

from schemas import AMLTransaction


project_root = Path(__file__).resolve().parents[2]
source_path = project_root / "data" / "samples" / "sample_transaction.txt"
source_text = source_path.read_text(encoding="utf-8")

model = ChatOllama(model="gemma4:e4b", temperature=0)
extractor = model.with_structured_output(AMLTransaction)

transaction = extractor.invoke(
    "Extract the transaction fields from the source text and return them in the "
    "requested schema. Use only information supported by the text. The schema "
    "requires a timestamp, but this sample gives only a date; represent that "
    "date as 00:00 UTC and do not imply that a transaction time was provided.\n\n"
    f"Source text:\n{source_text}"
)

print("Extracted transaction:")
print(transaction)
print("\nTimestamp note: if the source gave only a date, 00:00 UTC is a normalization assumption.")
