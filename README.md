# MedDoc AI 🩺

### AI-Powered Medical Document Assistant

MedDoc AI is an AI-powered medical document assistant designed to help users understand medical reports through **document-grounded Retrieval-Augmented Generation (RAG)**.

The system allows users to upload medical documents, extract and analyze their content, generate clear summaries, ask questions about the uploaded report, and understand medical parameters in a more accessible way.

> ⚠️ **Educational Prototype — Not for Clinical Use**
>
> MedDoc AI is intended for educational and research purposes. It does not replace a qualified healthcare professional and should not be used for diagnosis, treatment, or medical decision-making.

---

## ✨ Features

### 📄 Medical Document Upload

Upload supported medical documents through a simple drag-and-drop interface.

Supported formats:

- PDF
- TXT

The application automatically processes and indexes uploaded documents for subsequent analysis and question answering.

---

### 🤖 AI-Powered Medical Report Understanding

MedDoc AI uses **Groq-powered LLM inference** together with document-grounded retrieval to transform complex medical documents into easier-to-understand information.

The system can identify and explain:

- Patient information
- Report type
- Medical findings
- Laboratory measurements
- Abnormal results
- Reference ranges
- Medical terminology
- Report-specific observations

---

### 🔎 Retrieval-Augmented Generation (RAG)

MedDoc AI uses RAG to ground patient-specific answers in the uploaded medical document.

The general workflow is:

```text
Medical Document
       │
       ▼
Document Extraction
       │
       ▼
Text Chunking
       │
       ▼
Embedding / Indexing
       │
       ▼
Document Retrieval
       │
       ▼
Relevant Context
       │
       ▼
Groq LLM
       │
       ▼
Grounded Answer
```

This allows the assistant to answer questions using information from the user's uploaded document instead of relying only on general model knowledge.

---

### 🧬 Medical Parameter Explanation

MedDoc AI is designed to go beyond simple document retrieval.

When a user asks about a medical parameter, the system can combine:

**Patient-specific information from the uploaded document**

with

**General medical knowledge about the parameter.**

For example:

```text
User:
What is MCV?

MedDoc AI:
MCV stands for mean corpuscular volume. It describes
the average size of your red blood cells.

Your report shows an MCV of 72.1 fL, which is below
the reference range shown in the report.
```

This approach is intended to work across different types of medical reports, rather than being limited to one report type.

Potential examples include:

- Full Blood Count (FBC)
- Blood glucose reports
- HbA1c
- Lipid profiles
- Liver function tests
- Kidney/renal function tests
- Thyroid tests
- Urine reports
- ECG reports
- Echocardiography reports
- Radiology reports
- Pathology reports
- Cardiology reports

---

### 📊 Medical Report Summary

After processing a document, MedDoc AI can provide a structured report summary.

The dashboard can present information such as:

- Patient information
- Report type
- Main medical condition/finding
- Overall status
- Abnormal findings
- Measurements
- Follow-up information
- Important medical findings

The summary is designed to make lengthy medical documents easier to understand.

---

### 📚 Document-Grounded Citations

When an answer uses information from the uploaded report, MedDoc AI can provide a compact source reference.

Example:

```text
The patient's haemoglobin level is 9.6 g/dL, which is
below the reference range shown in the report.

Source: sample_fbc_1.pdf · Page 1
```

The system is designed to keep citations useful without exposing internal RAG or model implementation details to the user.

---

### 🗂️ Document History

The application maintains a history of uploaded documents.

Users can:

- View previous documents
- Open documents
- Start a conversation
- Delete documents
- Return to previously processed reports

---

### 🧠 Cached Report Analysis

MedDoc AI is designed to avoid unnecessarily regenerating the same medical analysis every time the page is refreshed.

Once an analysis has been generated, the system can reuse the stored analysis rather than repeatedly calling the AI provider.

This helps provide:

- More consistent results
- Reduced unnecessary AI requests
- Faster page loading
- Better resource usage

---

### 🎨 Responsive Dashboard

The frontend uses a dashboard-style interface with:

- Fixed sidebar navigation
- Documents view
- Report Summary
- Ask Questions
- History
- Responsive layouts
- Collapsible sidebar
- Desktop, tablet, and mobile support

Main navigation:

```text
📄 Documents
📊 Report Summary
💬 Ask Questions
🕘 History
```

The Documents page combines:

```text
┌──────────────────────┬─────────────────────────┐
│                      │                         │
│  Upload Document     │  Current Document       │
│                      │                         │
│  Drag & Drop         │  Filename               │
│  Choose File         │  Report Type            │
│                      │  Page                   │
│                      │  Content Size           │
│                      │  Format                 │
│                      │                         │
│                      │  Summarize Report       │
│                      │  Start Chat             │
│                      │  Delete                 │
│                      │                         │
└──────────────────────┴─────────────────────────┘
```

---

## 🏗️ System Architecture

The overall MedDoc AI architecture can be represented as:

```text
                    ┌─────────────────────┐
                    │      User           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Web Interface     │
                    │   MedDoc AI UI      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    FastAPI Backend  │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
        ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │  Document   │ │    RAG      │ │  Database   │
        │ Processing  │ │ Retrieval   │ │  / History  │
        └──────┬──────┘ └──────┬──────┘ └─────────────┘
               │               │
               └───────┬───────┘
                       ▼
               ┌───────────────┐
               │ Relevant      │
               │ Document      │
               │ Context       │
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
               │     Groq      │
               │      LLM      │
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
               │ Human-Friendly│
               │    Answer     │
               └───────────────┘
```

---

## 🛠️ Technology Stack

### Backend

- Python
- FastAPI
- RAG pipeline
- Document processing
- Vector-based retrieval
- Database-backed document history

### AI

- Groq API
- Groq-hosted LLM
- Retrieval-Augmented Generation (RAG)
- Medical document question answering
- Medical parameter explanation

### Frontend

- HTML
- CSS
- JavaScript
- Responsive dashboard UI

### Document Processing

- PDF extraction
- TXT processing
- Text chunking
- Document indexing
- Source/page tracking

---

## 🔐 AI Provider

MedDoc AI currently uses **Groq as the only AI provider**.
If the Groq service is unavailable, the application should return a controlled error instead of generating fabricated medical information.

---

## 🔄 Application Workflow

```text
1. User uploads medical document
             │
             ▼
2. Document is extracted
             │
             ▼
3. Text is processed and chunked
             │
             ▼
4. Document is indexed for retrieval
             │
             ▼
5. AI-generated report analysis
             │
             ▼
6. User views report summary
             │
             ▼
7. User asks questions
             │
             ▼
8. Relevant document context is retrieved
             │
             ▼
9. Groq generates a grounded response
             │
             ▼
10. User receives a concise explanation
```

---

## 🩺 Example Use Case

A user uploads a Full Blood Count report containing:

```text
Haemoglobin: 9.6 g/dL
MCV: 72.1 fL
HCT: 29.8%
```

The user can ask:

```text
What is my haemoglobin?
```

MedDoc AI can respond:

```text
Your haemoglobin level is 9.6 g/dL, which is below the
reference range shown in the report.
```

The user can then ask:

```text
What does haemoglobin mean?
```

The system can explain:

```text
Haemoglobin is a protein in red blood cells that carries
oxygen throughout the body.
```

The user can also ask:

```text
What does low haemoglobin mean?
```

The system can provide an educational explanation while avoiding an unsupported diagnosis.

---

## 🔒 Privacy & Security

Medical documents can contain highly sensitive information.

For development and testing:

- Do not upload real patient documents to public repositories.
- Do not commit API keys.
- Do not commit `.env` files.
- Do not commit private medical records.
- Use synthetic/sample medical reports for demonstrations.
- Do not expose patient information in logs unnecessarily.

---

## ⚠️ Medical Disclaimer

MedDoc AI is an **educational/research prototype**.

It is not:

- A medical diagnostic system
- A replacement for a doctor
- A clinical decision-support system
- A prescription system
- An emergency medical service

AI-generated explanations may be incomplete or incorrect.

Users should consult qualified healthcare professionals for medical interpretation, diagnosis, and treatment decisions.

---

## 🎯 Project Goals

The main goals of MedDoc AI are to:

- Make medical documents easier to understand
- Reduce the difficulty of reading complex medical reports
- Provide document-grounded question answering
- Explain medical terminology
- Highlight relevant report information
- Provide accessible medical-document interaction
- Explore RAG-based AI for medical document understanding
- Provide a foundation for future medical AI research

---

## 🔮 Future Development

Potential future improvements include:

- OCR for scanned medical documents
- Support for additional document formats
- Improved medical entity recognition
- Structured medical parameter extraction
- More advanced citation visualization
- Multilingual medical explanations
- Voice-based medical document interaction
- Enhanced evaluation and benchmarking
- Additional medical document types
- Integration with standardized medical terminology systems

---

## 👨‍💻 Project

**MedDoc AI**

AI-powered medical document understanding and question-answering system.

**Repository:**  
`https://github.com/HarisS2801/meddoc-ai`

---

## ⚖️ Disclaimer

This project is developed for **educational, research, and demonstration purposes only**.

It must not be used as a substitute for professional medical advice, diagnosis, or treatment.


# 👤 Author

**Haris**

Final Year Undergraduate

Department of Electrical and Electronic Engineering

University of Jaffna
