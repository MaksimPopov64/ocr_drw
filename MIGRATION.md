# Migration Guide: Switching to Qwen2.5-VL

This document details the changes made to migrate the OCR application from Mistral/LLaVA to **Qwen2.5-VL** as of January 2026.

## 1. Summary of Changes

We have replaced the previous two-stage pipeline (Tesseract OCR + LLaVA cleanup) with a single-stage **Vision-Language Model (VLM)** approach using `Qwen2.5-VL`.

### Key Benefits
- **Better Accuracy**: Qwen2.5-VL natively understands Russian text and document layout (tables, forms).
- **Simplified Stack**: Removed `tesseract`, `easyocr` and complex heuristic cleaning logic.
- **Robustness**: Improved resilience to noisy images via lighter preprocessing.

## 2. Codebase Updates

### New Files
- `qwen_processor.py`: Contains the `QwenOCRProcessor` class which handles image encoding and API communication with Ollama.
- `MIGRATION.md`: This file.

### Modified Files
- `app.py`:
    - Changed import: `MistralOCRProcessor` -> `QwenOCRProcessor`.
    - Updated initialization to use `qwen2.5-vl:7b` model.
- `requirements.txt`:
    - Removed `pytesseract` dependency (logic removed, though package might remain for other tools if needed).

### Deprecated Files
- `mistral_processor.py`: Code is superseded by `qwen_processor.py`. Can be archived or deleted.
- `ocr_processor.py`: Legacy processor, can be removed.

## 3. Migration Steps

### Step 1: Update Environment
Ensure you have the required Python packages:
```bash
pip install -r requirements.txt
```

### Step 2: Pull the Model
You must have [Ollama](https://ollama.com/) installed and running. Pull the Qwen2.5-VL model:
```bash
ollama pull qwen2.5-vl:7b
```
*Note: If `qwen2.5-vl` is not available under that exact tag, check the [Ollama library](https://ollama.com/library) for the correct tag (e.g. `qwen2.5-vl`).*

### Step 3: Verify Configuration
Check `.env` or environment variables. The default model is now set to `qwen2.5-vl:7b`.
```bash
export OLLAMA_MODEL=qwen2.5-vl:7b
```

### Step 4: Run Application
```bash
python app.py
```
The logs should show: `✅ Qwen2.5-VL OCR Processor initialized`.

## 4. Troubleshooting

- **Connection Error**: Ensure Ollama is running (`ollama serve`).
- **Model Not Found**: Run `ollama list` to see available models and update `OLLAMA_MODEL` env var if your tag differs.
- **JSON Parsing Error**: Qwen usually outputs valid JSON, but if the image is extremely blurry, it might fail. The new processor has validation steps to handle this.
