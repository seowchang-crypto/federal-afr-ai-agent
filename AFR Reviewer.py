import os
import json
import csv
import time
import pandas as pd
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts import evaluate_section_with_ai

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# File Paths
RULEBOOK_FILE = "Master_Audit_Rulebook.json"
OUTPUT_HTML = "AFR_Review_Results.html"
OUTPUT_CSV = "AFR_Review_Results.csv"
CHECKPOINT_FILE = "reviewer_checkpoint.json"

def load_file(filepath, is_json=False):
    if not os.path.exists(filepath):
        print(f"[!] Error: {filepath} not found. Please ensure it is in the same directory.")
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f) if is_json else f.read()

# =========================================================================
# THE RAG ENGINE (NEW)
# =========================================================================
def chunk_and_embed_afr(draft_afr_text):
    """
    Slices the massive AFR into smaller chunks with Hierarchical Breadcrumbs.
    Prevents Entity Confusion in multi-fund AFRs (e.g., General Fund vs WCF).
    """
    import re
    print("[*] Building AI Search Index (RAG) for the draft AFR...")
    
    raw_sections = re.split(r'\n(?=#+ )', "\n" + draft_afr_text)
    chunks = []
    active_headers = {}
    
    for section in raw_sections:
        if not section.strip(): continue
            
        lines = section.strip().split('\n')
        first_line = lines[0].strip()
        
        # Track the Markdown hierarchy
        if first_line.startswith('#'):
            level = len(first_line) - len(first_line.lstrip('#'))
            header_text = first_line.strip('# ').strip()
            
            active_headers[level] = header_text
            keys_to_remove = [k for k in active_headers.keys() if k > level]
            for k in keys_to_remove: 
                del active_headers[k]
                
        # Build the contextual breadcrumb (e.g., "Working Capital Fund > Note 4")
        current_breadcrumb = " > ".join([active_headers[k] for k in sorted(active_headers.keys())])
        
        paragraphs = section.split('\n\n')
        current_chunk = ""
        
        for p in paragraphs:
            if len(current_chunk) + len(p) < 3000:
                current_chunk += p + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(f"AFR ENTITY CONTEXT: [{current_breadcrumb}]\n\n{current_chunk.strip()}")
                current_chunk = p + "\n\n"
                
        if current_chunk.strip():
            chunks.append(f"AFR ENTITY CONTEXT: [{current_breadcrumb}]\n\n{current_chunk.strip()}")
        
    embeddings = []
    batch_size = 500
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        res = client.embeddings.create(input=batch, model="text-embedding-3-small")
        embeddings.extend([d.embedding for d in res.data])
        
    return chunks, np.array(embeddings)

def retrieve_relevant_afr_text(section_title, questions, afr_chunks, afr_embeddings, top_k=20):
    """
    Uses vector similarity to pull ONLY the AFR pages relevant to the current checklist section.
    """
    # Create a search query using the section title and main questions
    query_text = section_title + " " + " ".join([q.get("Main_Requirement_Question", {}).get("Audit_Question", "") for q in questions])
    
    # Embed the query
    query_emb = client.embeddings.create(input=query_text, model="text-embedding-3-small").data[0].embedding
    
    # Calculate Cosine Similarity (Dot product works because OpenAI embeddings are normalized)
    similarities = np.dot(afr_embeddings, query_emb)
    
    # Get the indices of the top K most relevant chunks
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    # Sort them back into document order so the text reads naturally for the AI
    sorted_top_indices = sorted(top_indices)
    
    # Stitch the highly relevant text together
    relevant_text = "\n\n...[IRRELEVANT TEXT SKIPPED]...\n\n".join([afr_chunks[idx] for idx in sorted_top_indices])
    return relevant_text

# =========================================================================
# EVALUATION & AGGREGATION
# =========================================================================
def get_best_evaluation(existing_eval_status, new_eval_status):
    ranks = {"Yes": 4, "No": 3, "Unverifiable": 2, "N/A": 1, "Error": 0, "Not Evaluated": 0}
    if ranks.get(new_eval_status, 0) > ranks.get(existing_eval_status, 0):
        return new_eval_status
    return existing_eval_status

#Location for evaluate_section_with_ai

def get_excel_column_name(n):
    result = ""
    while n >= 0:
        result = chr((n % 26) + 97) + result
        n = (n // 26) - 1
    return result

def append_csv_warning(eval_status, rationale):
    if eval_status in ["No", "N/A", "Unverifiable"]:
        warning = "\n\n[ACTION REQUIRED: Manual review needed. Risk of omission cannot be fully assessed solely based on the text provided.]"
        return f"{rationale}{warning}"
    return rationale

def append_html_warning(eval_status, rationale):
    if eval_status in ["No", "N/A", "Unverifiable"]:
        warning = "<br><br><span style='color: #c0392b; font-size: 0.9em;'><strong>[ACTION REQUIRED]:</strong> Manual review needed. Risk of omission cannot be fully assessed solely based on the text provided.</span>"
        return f"{rationale}{warning}"
    return rationale

def export_to_html(data, output_path):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Automated AFR Disclosure Review Results</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px auto; max-width: 1600px; line-height: 1.5; color: #333; }
            h1 { color: #2C3E50; border-bottom: 2px solid #2C3E50; padding-bottom: 10px; }
            h2 { color: #2980B9; margin-top: 40px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
            .legend-box { background-color: #f8f9fa; border: 1px solid #dee2e6; border-left: 5px solid #2C3E50; padding: 15px; margin-bottom: 25px; border-radius: 4px; }
            table { border-collapse: collapse; width: 100%; margin-top: 15px; background: white; font-size: 0.9em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            th, td { border: 1px solid #BDC3C7; padding: 12px; vertical-align: top; text-align: left; }
            th { background-color: #ECF0F1; color: #2C3E50; font-weight: bold; }
            .col-no { width: 4%; text-align: center; font-weight: bold; }
            .col-q { width: 35%; }
            .col-cat { width: 10%; font-weight: bold; color: #8E44AD; text-align: center; } 
            .col-ref { width: 12%; font-size: 0.9em; color: #7F8C8D; }
            .col-eval { width: 8%; text-align: center; }
            .col-rationale { width: 31%; font-size: 0.95em; }
            
            .badge { display: inline-block; padding: 5px 10px; border-radius: 15px; font-weight: bold; color: white; text-align: center; width: 90px;}
            .badge-yes { background-color: #27ae60; }
            .badge-no { background-color: #e74c3c; }
            .badge-na { background-color: #34495e; }
            .badge-unverifiable { background-color: #f39c12; color: #333; }
            .badge-none { background-color: #95a5a6; }
            
            .sub-row td.col-q { padding-left: 35px; color: #555; }
            .sub-row td.col-no { padding-left: 15px; text-align: left; }
            .sub-row td { background-color: #fafafa; border-top: 1px dashed #ddd; }
            .table-wrapper { margin-top: 10px; background: #fdfdfd; padding: 10px; border: 1px dashed #ccc; font-size: 0.85em; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>Automated AFR Disclosure Review Results</h1>
        <div class="legend-box">
            <strong>Evaluation Criteria:</strong><br>
            <span class="badge badge-yes">Yes</span> Met | 
            <span class="badge badge-no">No</span> Not Met | 
            <span class="badge badge-na">N/A</span> Not Applicable | 
            <span class="badge badge-unverifiable">Unverifiable</span> Requires Manual Review
        </div>
    """
    
    grouped = {}
    for item in data:
        sec = item.get("Section", "General Guidance")
        if sec not in grouped: grouped[sec] = []
        grouped[sec].append(item)
        
    global_counter = 1 
    
    for sec, items in grouped.items():
        valid_items = [i for i in items if i.get("Main_Requirement_Question", {}).get("Audit_Question", "").strip()]
        if not valid_items: continue
            
        html_content += f"<h2>{sec}</h2>"
        html_content += """
        <table>
            <thead>
                <tr>
                    <th class="col-no">No.</th>
                    <th class="col-q">Audit Questions</th>
                    <th class="col-cat">Category</th>
                    <th class="col-ref">Detailed Reference</th>
                    <th class="col-eval">AI Evaluation</th>
                    <th class="col-rationale">AI Rationale / Quotes</th>
                </tr>
            </thead>
            <tbody>
        """
        for item in valid_items:
            ref = item.get('Detailed_Reference', 'N/A')
            cat = item.get('Category', 'N/A')
            main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
            eval_main = item.get("AI_Main_Evaluation", "Not Evaluated")
            rat_main = append_html_warning(eval_main, item.get("AI_Main_Rationale", ""))
            
            table_content = item.get("Illustrative_Table", "null")
            if table_content and str(table_content).lower() != "null":
                main_q += f"<div class='table-wrapper'>{table_content}</div>"
            
            badge_class = "badge-none"
            if eval_main == "Yes": badge_class = "badge-yes"
            elif eval_main == "No": badge_class = "badge-no"
            elif eval_main == "N/A": badge_class = "badge-na"
            elif eval_main == "Unverifiable": badge_class = "badge-unverifiable"
                
            html_content += f"""
                <tr>
                    <td class="col-no">{global_counter}</td>
                    <td class="col-q"><strong>{main_q}</strong></td>
                    <td class="col-cat">{cat}</td>
                    <td class="col-ref">{ref}</td>
                    <td class="col-eval"><span class="badge {badge_class}">{eval_main}</span></td>
                    <td class="col-rationale">{rat_main}</td>
                </tr>
            """
            
            subs = item.get("Granular_Sub_Questions", [])
            for sub_idx, sub in enumerate(subs):
                letter = get_excel_column_name(sub_idx)
                sub_q = sub.get('Audit_Question', '')
                eval_sub = sub.get("AI_Evaluation", "Not Evaluated")
                rat_sub = append_html_warning(eval_sub, sub.get("AI_Rationale", ""))
                
                sub_badge_class = "badge-none"
                if eval_sub == "Yes": sub_badge_class = "badge-yes"
                elif eval_sub == "No": sub_badge_class = "badge-no"
                elif eval_sub == "N/A": sub_badge_class = "badge-na"
                elif eval_sub == "Unverifiable": sub_badge_class = "badge-unverifiable"
                
                html_content += f"""
                <tr class="sub-row">
                    <td class="col-no">{global_counter}{letter}</td>
                    <td class="col-q">{sub_q}</td>
                    <td class="col-cat"></td>
                    <td class="col-ref"></td>
                    <td class="col-eval"><span class="badge {sub_badge_class}">{eval_sub}</span></td>
                    <td class="col-rationale">{rat_sub}</td>
                </tr>
                """
            global_counter += 1
            
        html_content += "</tbody></table>"
    html_content += "</body></html>"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[+] Granular HTML Results Exported successfully to {output_path}")

# =========================================================================
# THE NEW INTEGRATION WRAPPER (RAG ENABLED)
# =========================================================================
def run_afr_review(draft_afr_path, rulebook_path=RULEBOOK_FILE, context_path="agency_context.txt"):
    print(f"[*] Initiating Automated AFR AI Reviewer on {draft_afr_path}...")
    
    rulebook = load_file(rulebook_path, is_json=True)
    draft_afr = load_file(draft_afr_path, is_json=False)
    agency_context = load_file(context_path, is_json=False) or "No specific agency context provided."
    
    if not rulebook or not draft_afr:
        raise FileNotFoundError("Could not load Rulebook or AFR file.")
        
    grouped_rules = {}
    valid_rules_count = 0
    for idx, item in enumerate(rulebook):
        main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "").strip()
        if not main_q: continue 
            
        sec = item.get("Section", "General Guidance")
        if sec not in grouped_rules: grouped_rules[sec] = []
            
        item_copy = item.copy()
        item_copy["master_idx"] = idx 
        grouped_rules[sec].append(item_copy)
        valid_rules_count += 1
        
    print(f"[*] Loaded {valid_rules_count} valid disclosure rules to evaluate.")
    
    # 1. BUILD THE RAG INDEX
    afr_chunks, afr_embeddings = chunk_and_embed_afr(draft_afr)
        
    completed_evals = {}
    if os.path.exists(CHECKPOINT_FILE):
        print("[i] Found existing evaluations. Resuming from checkpoint...")
        completed_evals = load_file(CHECKPOINT_FILE, is_json=True)
        
    total_sections = len(grouped_rules)
    
    for i, (section, questions) in enumerate(grouped_rules.items()):
        if section in completed_evals:
            print(f"  -> Skipping Section {i+1}/{total_sections}: {section} (Found in Checkpoint)")
            continue
            
        print(f"  -> Evaluating Section {i+1}/{total_sections}: {section} ({len(questions)} rules)...")
        
        # 2. RETRIEVE RELEVANT TEXT (The Magic of RAG)
        relevant_text = retrieve_relevant_afr_text(section, questions, afr_chunks, afr_embeddings, top_k=8)
        
        # 3. EVALUATE (Fast, single-call execution)
        evaluations = evaluate_section_with_ai(section, questions, relevant_text, agency_context)
        
        if evaluations:
            completed_evals[section] = evaluations
            with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                json.dump(completed_evals, f)

    print("\n[*] Merging AI findings into Master Rulebook...")
    
    # Update the rulebook with findings
    for section, evals in completed_evals.items():
        for ev in evals:
            idx = ev.get("master_idx")
            if idx is not None and 0 <= idx < len(rulebook):
                rulebook[idx]["AI_Main_Evaluation"] = ev.get("main_evaluation", "Error")
                rulebook[idx]["AI_Main_Rationale"] = ev.get("main_rationale", "No rationale provided.")
                
                sub_eval_dict = {s["sub_idx"]: s for s in ev.get("sub_evaluations", [])}
                
                for j, sub in enumerate(rulebook[idx].get("Granular_Sub_Questions", [])):
                    match = sub_eval_dict.get(j, {})
                    sub["AI_Evaluation"] = match.get("evaluation", "Not Evaluated")
                    sub["AI_Rationale"] = match.get("rationale", "")
                
    export_to_html(rulebook, OUTPUT_HTML)
    
    # Generate the Pandas DataFrame for Streamlit
    df_rows = []
    global_counter = 1
    
    for item in rulebook:
        main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "").strip()
        if not main_q: continue 
        
        eval_main = item.get("AI_Main_Evaluation", "Not Evaluated")
        rat_main = append_csv_warning(eval_main, item.get("AI_Main_Rationale", ""))
        
        df_rows.append({
            "No.": str(global_counter),
            "Audit Questions": main_q,
            "Category": item.get("Category", ""),
            "Detailed Reference": item.get("Detailed_Reference", ""),
            "AI Evaluation": eval_main,
            "AI Rationale": rat_main,
            "Source_Framework": item.get("Source_Framework", "")
        })
        
        subs = item.get("Granular_Sub_Questions", [])
        for sub_idx, sub in enumerate(subs):
            letter = get_excel_column_name(sub_idx) 
            
            # Check for sub-question tables
            sub_table = sub.get("Illustrative_Table", "null")
            if sub_table and str(sub_table).lower() != "null":
                    sub_q_text += f"<div class='table-wrapper'>{sub_table}</div>"
            
            eval_sub = sub.get("AI_Evaluation", "Not Evaluated")
            rat_sub = append_csv_warning(eval_sub, sub.get("AI_Rationale", ""))
            
            df_rows.append({
                "No.": f"    {global_counter}{letter}",
                "Audit Questions": f"    • {sub.get('Audit_Question', '')}",
                "Category": "", 
                "Detailed Reference": "",
                "AI Evaluation": eval_sub,
                "AI Rationale": rat_sub,
                "Source_Framework": ""
            })
        global_counter += 1
        
    print("[+] Evaluation complete. Handing results back to UI.")
    return pd.DataFrame(df_rows)


if __name__ == "__main__":
    test_draft = "HUD_afr2025_Converted.md" 
    if os.path.exists(test_draft):
        result_df = run_afr_review(test_draft)
        print("\n--- DataFrame Sample ---")
        print(result_df.head())
    else:
        print(f"Test file '{test_draft}' not found. Cannot run standalone test.")