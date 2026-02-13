"""One-off script to verify extraction with updated prompts produces numeric_thresholds."""
import asyncio
import json
import os
import re
import sys
import tempfile
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
        from google import genai
        from google.genai import types
        from jinja2 import Environment, FileSystemLoader

        from extraction_service.schemas.criteria import ExtractionResult
    except ImportError as e:
        print(f"Import error: {e}")
        return

    tmp_path = None
    uploaded_file = None
    client = None

    try:
        pdf_bytes = pdf_path.read_bytes()

        # Write PDF to temp file for File API upload
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # Instantiate client
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        # Upload via File API
        uploaded_file = client.files.upload(file=tmp_path)

        # Render prompts directly using Jinja2
        prompts_dir = Path(__file__).parent.parent / "src" / "extraction_service" / "prompts"
        env = Environment(loader=FileSystemLoader(str(prompts_dir)))
        system_prompt = env.get_template("system.jinja2").render()
        user_prompt = env.get_template("user.jinja2").render(title=pdf_path.stem)

        print(f"Calling Gemini ({model_name})...")
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[uploaded_file, user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            ),
        )

        # Parse result
        if response.parsed is not None:
            result = response.parsed
        else:
            result = ExtractionResult.model_validate_json(response.text)

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
    finally:
        # Clean up temp file
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                print(f"Warning: Failed to delete temp file {tmp_path}: {cleanup_err}")

        # Clean up uploaded file
        if uploaded_file and client:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as cleanup_err:
                print(f"Warning: Failed to delete uploaded file {uploaded_file.name}: {cleanup_err}")


if __name__ == "__main__":
    asyncio.run(main())
