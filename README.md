🏛️ Automated Federal Financial Disclosure Engine (AFR-AI)

📌 Executive Summary

The Agency Financial Report (AFR) review process is historically a highly manual, time-intensive audit requiring deep domain expertise in Federal GAAP (SFFAS) and OMB Circular A-136.

AFR-AI is an enterprise-grade, multi-agent ETL (Extract, Transform, Load) pipeline that automates the extraction, consolidation, and execution of federal financial compliance checklists. By combining a 3-agent LLM architecture (Triage, Extraction, and Formatting) with a custom Retrieval-Augmented Generation (RAG) framework, this system accelerates a multi-week, 150+ page compliance review into a highly accurate, deterministic, CPA-grade audit matrix.

🔒 Note on Source Code & IP: To protect the proprietary intellectual property of the underlying heuristic prompts, routing locks, and extraction logic, the core generation scripts have been abstracted from this public repository. The provided code demonstrates the data pipeline, RAG architecture, and orchestration layers.

⚠️ Disclaimer: Human-in-the-Loop (HITL) Requirement This pipeline is engineered as an auditor-assistive tool designed to drastically accelerate the compliance review process and reduce manual data-gathering fatigue. It does not replace professional human judgment. While the pipeline utilizes advanced mitigation strategies to prevent AI hallucinations, LLMs can occasionally misinterpret highly nuanced regulatory contexts. All final compliance decisions reside strictly with the auditing professional.

🚀 Advanced AI Capabilities & Engineering Triumphs

This project serves as a proving ground for applying generative AI to strict, zero-tolerance financial environments. Building this required defeating several inherent flaws in Large Language Models. Key engineering achievements include:

Agentic Semantic Routing & "Hijack" Prevention: Engineered a Triage Agent capable of autonomously mapping raw regulatory text to a massive Table of Contents. Successfully developed "Absolute Pre-Routing Overrides" to defeat LLM semantic hallucinations—specifically overcoming Token Gravity Hijacking (where heavy domain words pull the AI off-topic) and Negative Constraint Reversals (the "Pink Elephant" bug).

Dense Paragraph Splitting & Table Custody: Built an Extraction Agent that surgically shatters run-on, multi-command regulatory paragraphs into distinct, granular JSON objects. Implemented a strict "Table Custody" protocol to ensure illustrative Markdown tables remain physically tethered to their corresponding textual commands, preventing data orphaning.

Hybrid Deterministic Deduplication: Implemented a Python-driven fuzzy matching interceptor (via difflib) to catch and silently drop extraction variances, proving that traditional code and probabilistic LLMs must be orchestrated together to maintain perfect data integrity.

Zero-Shot Format Adherence: Designed a Formatting Agent utilizing few-shot CPA examples to convert complex, nested compliance lists (e.g., Stem-and-Branch grammar) into strict, binary Yes/No/N/A audit questions.

🏗️ High-Level System Architecture (The Multi-Agent Workflow)

The pipeline is built on decoupled pillars to ensure data integrity, scalability, and modularity:

Agent 1: The Semantic Router (Triage): Ingests chunked regulatory PDFs, evaluates the text for actionable accounting commands, and locks the text to the correct hierarchical section using deterministic regex fallbacks and semantic guardrails.

Agent 2: The Surgeon (Extraction): Takes dense, approved paragraphs and splits them into distinct compliance rules, preserving "boilerplate" narrative requirements while restructuring actionable lists.

Agent 3: The CPA (Formatting): Processes the granular JSON payloads and translates them into an auditor-ready compliance matrix using strict grammar constraints.

The Execution Engine: The front-end application that vectorizes a Draft AFR, performs targeted similarity searches against the generated rulebook, and outputs an evidence-backed compliance matrix (JSON/CSV/HTML).

🛠️ Tech Stack

AI & Machine Learning: OpenAI API (GPT-4o, text-embedding-3-small), Semantic Vector Search, Multi-Agent Orchestration.

Cloud & Document Intelligence: Microsoft Azure AI (Document Intelligence / Layout Models) for unstructured PDF parsing and multi-modal OCR.

Languages & Data: Python, Pandas, NumPy, JSON, Markdown, Regex.

Domain Intersection: U.S. GAAP, Technical Accounting, Regulatory Compliance Auditing.

📈 Known Limitations & Future Architecture (Continuous Integration)

Building AI for federal accounting requires knowing the exact ceiling of probabilistic instruction-following. Current areas of ongoing research and architectural evolution include:

Horizontal Scaling to SFFAS (Phase 2): Phase 1 successfully proved the multi-agent extraction architecture on the 150-page OMB Circular A-136. The architecture is designed to be framework-agnostic. Phase 2 of this project will scale the ETL pipeline to ingest and map the overarching FASAB/SFFAS corpus. This horizontal expansion is currently roadmapped as a future milestone to strategically manage API compute costs while the core deterministic routing logic is finalized.

Tuning the Semantic Consolidator (Rule Merging): The middle layer of the pipeline is designed to ingest rulebooks from different frameworks (e.g., OMB vs. FASAB) and intelligently merge overlapping mandates. Ongoing development is focused on stress-testing the AI's similarity-matching thresholds to ensure it perfectly consolidates redundant rules without accidentally dropping highly nuanced, framework-specific exceptions.

RAG Execution Engine Edge-Case Testing: The final phase of the pipeline—vectorizing a Draft AFR and executing the compliance checklist against it—is currently undergoing rigorous edge-case testing. Future updates will focus on optimizing the RAG retrieval parameters (e.g., dynamic chunking and Top-K tuning) to improve the LLM's ability to accurately retrieve and verify compliance evidence buried deep within multi-page, unstructured financial tables.

Hybrid Deterministic Interceptors: Transitioning the pipeline's semantic routing from pure LLM instruction-following to a Regex-first architecture, utilizing Python to hard-lock highly regulated vocabulary (e.g., FCRA) before handing the payload to the LLM to save compute costs and guarantee zero routing hallucinations.

📬 Let's Connect

I am actively seeking feedback, constructive critiques, and discussions on how to improve this architecture. If you are interested in the intersection of Artificial Intelligence, Data Engineering, and Strategic Finance, I would love to connect!

LinkedIn: [www.linkedin.com/in/seo-chang]

Email: [seo.w.chang@gmail.com]
