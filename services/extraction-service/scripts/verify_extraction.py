"""One-off script to verify extraction with updated prompts produces numeric_thresholds."""
import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

# Set DATABASE_URL before any imports that might need it
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# Add service to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def main():
    # Find a real protocol PDF (skip test-protocol.pdf which is 0 KB)
    uploads_dir = Path(__file__).parent.parent.parent.parent / "uploads" / "protocols"
    pdf_path = None
    for proto_dir in sorted(uploads_dir.iterdir()):
        if proto_dir.is_dir():
            for f in proto_dir.iterdir():
                if f.suffix == ".pdf" and f.stat().st_size > 1000:
                    pdf_path = f
                    break
        if pdf_path:
            break

    if not pdf_path:
        print("No protocol PDFs found in uploads/protocols/")
        return

    print(f"Using PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024:.0f} KB)")

    try:
        from jinja2 import Environment, FileSystemLoader
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI
        from extraction_service.schemas.criteria import ExtractionResult
    except ImportError as e:
        print(f"Import error: {e}")
        return

    try:
        pdf_bytes = pdf_path.read_bytes()
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        pdf_data_uri = f"data:application/pdf;base64,{pdf_base64}"

        # Render prompts directly using Jinja2
        prompts_dir = Path(__file__).parent.parent / "src" / "extraction_service" / "prompts"
        env = Environment(loader=FileSystemLoader(str(prompts_dir)))
        system_prompt = env.get_template("system.jinja2").render()
        user_prompt = env.get_template("user.jinja2").render(title=pdf_path.stem)

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            vertexai=True,
            project=os.getenv("GCP_PROJECT_ID"),
            location=os.getenv("GCP_REGION", "us-central1"),
        )
        structured_llm = llm.with_structured_output(ExtractionResult)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=[
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": pdf_data_uri}},
            ]),
        ]

        print(f"Calling Gemini ({model_name})...")
        result = await structured_llm.ainvoke(messages)
        if isinstance(result, dict):
            result = ExtractionResult(**result)

        # Analyze results
        total = len(result.criteria)
        numeric_pattern = re.compile(
            r'\d+\.?\d*\s*(year|mg|%|kg|score|mL|mmol|unit|day|week|month|hour|mcg|g/dL|mm)',
            re.IGNORECASE,
        )
        with_numeric_content = [c for c in result.criteria if numeric_pattern.search(c.text)]
        with_thresholds = [c for c in result.criteria if c.numeric_thresholds]
        with_temporal = [c for c in result.criteria if c.temporal_constraint]
        conditional = [c for c in result.criteria if c.assertion_status == "CONDITIONAL"]
        with_conditions = [c for c in result.criteria if c.conditions]

        print(f"\n{'='*60}")
        print("EXTRACTION RESULTS")
        print(f"{'='*60}")
        print(f"Total criteria extracted:              {total}")
        print(f"Criteria with numeric content:         {len(with_numeric_content)}")
        print(f"Criteria with populated thresholds:    {len(with_thresholds)}")
        if with_numeric_content:
            rate = len(with_thresholds) / len(with_numeric_content) * 100
            print(f"Threshold population rate:             {rate:.0f}% (of criteria with numeric content)")
        print(f"Criteria with temporal_constraint:     {len(with_temporal)}")
        print(f"Criteria with CONDITIONAL status:      {len(conditional)}")
        print(f"Criteria with populated conditions:    {len(with_conditions)}")
        if conditional:
            cond_rate = len(with_conditions) / len(conditional) * 100
            print(f"Conditions population rate:            {cond_rate:.0f}% (of CONDITIONAL criteria)")

        # Show first 5 criteria with thresholds
        if with_thresholds:
            print(f"\n{'='*60}")
            print("SAMPLE CRITERIA WITH THRESHOLDS (first 5)")
            print(f"{'='*60}")
            for c in with_thresholds[:5]:
                text = c.text[:120] + ("..." if len(c.text) > 120 else "")
                print(f"\nText: {text}")
                print(f"  Thresholds: {json.dumps([t.model_dump() for t in c.numeric_thresholds])}")
        else:
            print("\nWARNING: No criteria have populated numeric_thresholds!")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
