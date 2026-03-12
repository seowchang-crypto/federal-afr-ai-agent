import json
import csv
import os
import time
import re
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts import ai_map_section
from private_prompts import ai_deduplicate_and_merge

# Load API Key
load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# File Paths
OMB_FILE = "OMB_A136_Checklist_FY25.json" 
SFFAS_FILE = "2025_SFFAS_Disclosure_Checklist.json" 

OUTPUT_JSON = "Master_Audit_Rulebook.json"
OUTPUT_CSV = "Master_Audit_Rulebook.csv"
OUTPUT_MD = "Master_Audit_Rulebook.md"
OUTPUT_HTML = "Master_Audit_Rulebook.html"

def load_json(filepath):
    if not os.path.exists(filepath):
        print(f"[!] Warning: {filepath} not found.")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, dict) and "Checklist" in data:
            return data["Checklist"]
        elif isinstance(data, list):
            return data
        return []

def format_audit_question_text(item, use_markdown=False):
    main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "").strip()
    subs = item.get("Granular_Sub_Questions", [])
    if not subs: return main_q
        
    combined = f"{main_q}\n"
    for sub in subs:
        sub_text = sub.get("Audit_Question", "").strip()
        bullet = "- " if use_markdown else "  • "
        combined += f"{bullet}{sub_text}\n"
    return combined.strip()

#Location for ai_map_section

#Location for ai_deduplicate_and_merge

def get_section_sort_key(item):
    """
    Translates OMB Section strings (e.g., 'II.3.8.33 Note 33') into mathematical 
    arrays (e.g., [2, 3, 8, 33]) so Python can sort them in perfect structural order.
    """
    section_str = item.get("Section", "General Guidance")
    
    # If it's general guidance, force it to the very top
    if not section_str.startswith(('I.', 'II.', 'III.', 'IV.', 'V.', 'VI.', 'VII.', 'VIII.', 'IX.', 'X.')):
        return ([0], section_str)
        
    # Isolate the numbering part before the first space (e.g., "II.3.8.33")
    numbering_part = section_str.split(' ')[0]
    parts = numbering_part.split('.')
    
    # Map Roman numerals to integers
    roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}
    
    sort_tuple = []
    for i, part in enumerate(parts):
        if i == 0:
            sort_tuple.append(roman_map.get(part, 99))
        else:
            # Strip out any trailing non-numeric characters (like "A" in "II.3.8.A")
            clean_num = re.sub(r'\D', '', part)
            if clean_num:
                sort_tuple.append(int(clean_num))
            else:
                sort_tuple.append(0)
                
    return (sort_tuple, section_str)

def consolidate_data_with_ai():
    omb_data = load_json(OMB_FILE)
    sffas_data = load_json(SFFAS_FILE)
    
    if not omb_data or not sffas_data:
        print("[!] Missing JSON data. Ensure extraction scripts have finished.")
        return []
        
    CHECKPOINT_FILE = "consolidation_checkpoint.json"
    start_index = 0
    
    if os.path.exists(CHECKPOINT_FILE):
        print(f"\n[i] Found checkpoint! Resuming consolidation...")
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            checkpoint_data = json.load(f)
            omb_data = checkpoint_data["omb_data"]
            start_index = checkpoint_data["start_index"]
            print(f"[i] Skipping the first {start_index} SFFAS rules...\n")
    else:
        for item in omb_data: item["Source_Framework"] = "OMB A-136"
        for item in sffas_data: item["Source_Framework"] = "SFFAS"
        
    omb_index = {"General Guidance": []} 
    for idx, item in enumerate(omb_data):
        sec = item.get("Section", "General Guidance")
        if sec not in omb_index:
            omb_index[sec] = []
        omb_index[sec].append({"master_idx": idx, "data": item})
        
    omb_section_titles = list(omb_index.keys())
    total_sffas = len(sffas_data)
    
    print(f"[*] PRODUCTION RUN ENGAGED: Processing SFFAS rules {start_index} to {total_sffas}...")
    
    for i in range(start_index, total_sffas):
        sffas_item = sffas_data[i]
        print(f"  -> Sending SFFAS rule {i+1}/{total_sffas} to OpenAI...")
        
        mapped_section = ai_map_section(sffas_item, omb_section_titles)
        if mapped_section not in omb_index:
            mapped_section = "General Guidance"
            
        section_items_only = [x["data"] for x in omb_index[mapped_section]]
        decision = ai_deduplicate_and_merge(sffas_item, section_items_only)
        
        if decision.get("action") == "consolidate" and "omb_match_index" in decision:
            local_idx = decision["omb_match_index"]
            
            if isinstance(local_idx, list) and len(local_idx) > 0:
                local_idx = local_idx[0]
                
            if isinstance(local_idx, int) and 0 <= local_idx < len(omb_index[mapped_section]):
                master_idx = omb_index[mapped_section][local_idx]["master_idx"]
                
                # 1. Merge Framework Tag
                omb_data[master_idx]["Source_Framework"] = "OMB A-136 & SFFAS"
                
                # 2. Consolidate References seamlessly
                existing_ref = str(omb_data[master_idx].get("Detailed_Reference", "")).strip()
                new_ref = str(sffas_item.get("Detailed_Reference", "")).strip()
                if new_ref and new_ref.lower() != "null" and new_ref not in existing_ref:
                    if existing_ref:
                        omb_data[master_idx]["Detailed_Reference"] = f"{existing_ref}; {new_ref}"
                    else:
                        omb_data[master_idx]["Detailed_Reference"] = new_ref

                # 3. Consolidate Categories seamlessly
                existing_cat = str(omb_data[master_idx].get("Category", "")).strip()
                new_cat = str(sffas_item.get("Category", "")).strip()
                if new_cat and new_cat.lower() != "null" and new_cat not in existing_cat:
                    if existing_cat:
                        omb_data[master_idx]["Category"] = f"{existing_cat} / {new_cat}"
                    else:
                        omb_data[master_idx]["Category"] = new_cat
                        
                # 4. Consolidate Tables
                existing_table = str(omb_data[master_idx].get("Illustrative_Table", "null")).strip()
                new_table = str(sffas_item.get("Illustrative_Table", "null")).strip()
                if new_table.lower() != "null":
                    if existing_table.lower() != "null":
                        # If both have tables, concatenate them with a markdown divider
                        omb_data[master_idx]["Illustrative_Table"] = f"{existing_table}\n\n---\n\n{new_table}"
                    else:
                        omb_data[master_idx]["Illustrative_Table"] = new_table

                # 5. Consolidate Figures
                existing_fig = str(omb_data[master_idx].get("Illustrative_Figure_Path", "null")).strip()
                new_fig = str(sffas_item.get("Illustrative_Figure_Path", "null")).strip()
                if new_fig.lower() != "null":
                    if existing_fig.lower() != "null":
                        omb_data[master_idx]["Illustrative_Figure_Path"] = f"{existing_fig} ; {new_fig}"
                    else:
                        omb_data[master_idx]["Illustrative_Figure_Path"] = new_fig
                
                # Notice: We completely REMOVED the code that appended the SFFAS text to the Sub_Questions!
                # It now acts as a pure Reference Consolidation.

        else:
            # If no match is found, append it as a brand new rule in the section
            sffas_item["Section"] = mapped_section
            omb_data.append(sffas_item)
            new_idx = len(omb_data) - 1
            omb_index[mapped_section].append({"master_idx": new_idx, "data": sffas_item})
            
        temp_cp = CHECKPOINT_FILE + ".tmp"
        with open(temp_cp, 'w', encoding='utf-8') as f:
            json.dump({
                "start_index": i + 1, 
                "omb_data": omb_data
            }, f)
        os.replace(temp_cp, CHECKPOINT_FILE)
        time.sleep(0.2) 
        
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
            
    return omb_data

def export_to_json(data, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"[+] JSON Exported successfully to {output_path}")

def get_excel_column_name(n):
    result = ""
    while n >= 0:
        result = chr((n % 26) + 97) + result
        n = (n // 26) - 1
    return result

def export_to_csv(data, output_path):
    headers = [
        "OMB Section", "No.", "Audit Questions", "Category", "Detailed Reference", 
        "Yes / No / N/A", "Note", "Source_Framework", "Has_Visuals", "Table Content" # <--- Add header
    ]
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        question_counter = 1
        for item in data:
            main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
            if not main_q: continue
            
            table_content = item.get("Illustrative_Table", "null")
            figure_path = item.get("Illustrative_Figure_Path", "null")
            has_visuals = "Yes" if (str(table_content).lower() != "null" or str(figure_path).lower() != "null") else "No"
            
            writer.writerow({
                "OMB Section": item.get("Section", "General Guidance"),
                "No.": str(question_counter),
                "Audit Questions": main_q,
                "Category": item.get("Category", "Uncategorized"),
                "Detailed Reference": item.get("Detailed_Reference", ""),
                "Yes / No / N/A": "",
                "Note": "",
                "Source_Framework": item.get("Source_Framework", ""),
                "Has_Visuals": has_visuals,
                "Table Content": item.get("Illustrative_Table", "null") # <--- Add mapping
            })
            
            subs = item.get("Granular_Sub_Questions", [])
            for sub_idx, sub in enumerate(subs):
                letter = get_excel_column_name(sub_idx) 
                sub_text = sub.get("Audit_Question", "")
                
                writer.writerow({
                    "OMB Section": item.get("Section", "General Guidance"),
                    "No.": f"{question_counter}{letter}",
                    "Audit Questions": f"    • {sub_text}",
                    "Category": "", 
                    "Detailed Reference": "", 
                    "Yes / No / N/A": "",
                    "Note": "",
                    "Source_Framework": "",
                    "Has_Visuals": "No"
                })
                
            question_counter += 1
            
    print(f"[+] CSV Exported successfully to {output_path}")

def export_to_markdown(data, output_path):
    grouped = {}
    for item in data:
        section = item.get("Section", "General Guidance")
        if section not in grouped: grouped[section] = []
        grouped[section].append(item)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Master Audit Rulebook\n\n")
        for section, items in grouped.items():
            f.write(f"## {section}\n\n")
            for item in items:
                main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
                if not main_q: continue
                f.write(f"> **Original Text:** {item.get('Original_Requirement_Text', 'N/A')}\n>\n")
                f.write(f"### {format_audit_question_text(item, use_markdown=True)}\n")
                f.write(f"\n**Category:** {item.get('Category', 'N/A')} | **Reference:** {item.get('Detailed_Reference', 'N/A')}\n\n")
                
                table_content = item.get("Illustrative_Table", "null")
                if table_content and str(table_content).lower() != "null":
                    f.write(f"{table_content}\n\n")
                
                figure_path = item.get("Illustrative_Figure_Path", "null")
                if figure_path and str(figure_path).lower() != "null":
                    clean_path = figure_path.replace("![", "").replace("]", "").replace("(", "").replace(")", "").replace("Figure", "").strip()
                    f.write(f"![Illustrative Figure]({clean_path})\n\n")
                    
            f.write("---\n\n")
    print(f"[+] Markdown Exported successfully to {output_path}")

def export_to_html(data, output_path="Master_Audit_Rulebook.html"):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Agency Financial Report Comprehensive Disclosure Checklist</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px auto; max-width: 1400px; line-height: 1.5; color: #333; }
            h1 { color: #2C3E50; border-bottom: 2px solid #2C3E50; padding-bottom: 10px; }
            h2 { color: #2980B9; margin-top: 40px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
            table { border-collapse: collapse; width: 100%; margin-top: 15px; background: white; font-size: 0.9em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            th, td { border: 1px solid #BDC3C7; padding: 12px; vertical-align: top; text-align: left; }
            th { background-color: #ECF0F1; color: #2C3E50; font-weight: bold; }
            .col-no { width: 4%; text-align: center; font-weight: bold; }
            .col-q { width: 44%; }
            .col-cat { width: 10%; font-size: 0.9em; font-weight: bold; color: #C0392B; }
            .col-ref { width: 14%; font-size: 0.9em; color: #7F8C8D; }
            .col-check { width: 10%; text-align: center; }
            .col-note { width: 18%; }
            .table-wrapper { margin-top: 15px; overflow-x: auto; background: #fdfdfd; padding: 10px; border: 1px dashed #ccc; }
            .figure-wrapper img { max-width: 100%; height: auto; border: 1px solid #ccc; margin-top: 10px; }
            .sub-question-row td.col-q { padding-left: 35px; border-top: 1px dashed #eee; color: #444; }
            .sub-question-row td { border-top: 1px dashed #eee; }
            .framework-badge { display: inline-block; padding: 2px 6px; background: #34495E; color: white; border-radius: 3px; font-size: 0.8em; margin-bottom: 5px; }
        </style>
    </head>
    <body>
        <h1>Agency Financial Report Comprehensive Disclosure Checklist</h1>
    """
    
    grouped = {}
    for item in data:
        sec = item.get("Section", "General Guidance")
        if sec not in grouped: grouped[sec] = []
        grouped[sec].append(item)
        
    global_counter = 1 
    
    for sec, items in grouped.items():
        html_content += f"<h2>{sec}</h2>"
        html_content += """
        <table>
            <thead>
                <tr>
                    <th class="col-no">No.</th>
                    <th class="col-q">Audit Questions</th>
                    <th class="col-cat">Category</th>
                    <th class="col-ref">Detailed Reference</th>
                    <th class="col-check">Yes / No / N/A</th>
                    <th class="col-note">Note</th>
                </tr>
            </thead>
            <tbody>
        """
        for item in items:
            cat = item.get('Category', 'N/A')
            ref = item.get('Detailed_Reference', 'N/A')
            framework = item.get('Source_Framework', '')
            
            main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
            subs = item.get("Granular_Sub_Questions", [])
            
            q_html = f"<div class='framework-badge'>{framework}</div><br>" if framework else ""
            q_html += f"<strong>{main_q}</strong>"
            
            table_content = item.get("Illustrative_Table", "null")
            if table_content and str(table_content).lower() != "null":
                q_html += f"<div class='table-wrapper'>{table_content}</div>"
                
            figure_path = item.get("Illustrative_Figure_Path", "null")
            if figure_path and str(figure_path).lower() != "null":
                clean_path = figure_path.replace("![", "").replace("]", "").replace("(", "").replace(")", "").replace("Figure", "").strip()
                q_html += f"<div class='figure-wrapper'><img src='{clean_path}' alt='Illustrative Diagram'/></div>"
                
            html_content += f"""
                <tr>
                    <td class="col-no">{global_counter}</td>
                    <td class="col-q">{q_html}</td>
                    <td class="col-cat">{cat}</td>
                    <td class="col-ref">{ref}</td>
                    <td class="col-check"></td>
                    <td class="col-note"></td>
                </tr>
            """
            
            for sub_idx, sub in enumerate(subs):
                letter = get_excel_column_name(sub_idx) 
                sub_q_text = sub.get('Audit_Question', '')
                
                # Check for sub-question tables
                sub_table = sub.get("Illustrative_Table", "null")
                if sub_table and str(sub_table).lower() != "null":
                    sub_q_text += f"<div class='table-wrapper'>{sub_table}</div>"
                
                html_content += f"""
                <tr class="sub-question-row">
                    <td class="col-no">{global_counter}{letter}</td>
                    <td class="col-q">{sub_q_text}</td>
                    <td class="col-cat"></td>
                    <td class="col-ref"></td>
                    <td class="col-check"></td>
                    <td class="col-note"></td>
                </tr>
                """
                
            global_counter += 1
            
        html_content += "</tbody></table>"
        
    html_content += "</body></html>"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[+] HTML Web Page Exported successfully to {output_path}")

if __name__ == "__main__":
    print("Initiating Master Rulebook Consolidation (FULL PRODUCTION RUN)...")
    
    original_omb_data = load_json(OMB_FILE)
    chronological_sections = []
    for item in original_omb_data:
        sec = item.get("Section", "General Guidance")
        if sec not in chronological_sections:
            chronological_sections.append(sec)

    master_data = consolidate_data_with_ai()
    
    if master_data:
        grouped_master = {}
        for item in master_data:
            sec = item.get("Section", "General Guidance")
            if sec not in grouped_master:
                grouped_master[sec] = []
            grouped_master[sec].append(item)
            
        ordered_master_data = []
        for sec in chronological_sections:
            if sec in grouped_master:
                ordered_master_data.extend(grouped_master[sec])
                
        for sec, items in grouped_master.items():
            if sec not in chronological_sections:
                ordered_master_data.extend(items)

        # THE UPGRADE: Dynamically recalculate the Source_Framework badge based on the actual citation
        print("\n[*] Realigning Framework Meta Tags to match Detailed References...")
        for item in ordered_master_data:
            ref = str(item.get("Detailed_Reference", "")).upper()
            if "OMB" in ref and "SFFAS" in ref:
                item["Source_Framework"] = "OMB A-136 & SFFAS"
            elif "OMB" in ref:
                item["Source_Framework"] = "OMB A-136"
            elif "SFFAS" in ref:
                item["Source_Framework"] = "SFFAS"

        # --- NEW CODE GOES HERE ---
        print("[*] Enforcing Strict Structural Sort (OMB Table of Contents order)...")
        ordered_master_data.sort(key=get_section_sort_key)
        # --------------------------

        print("[*] Generating perfectly aligned Master Deliverables...")
        export_to_json(ordered_master_data, OUTPUT_JSON)
        export_to_csv(ordered_master_data, OUTPUT_CSV)
        export_to_markdown(ordered_master_data, OUTPUT_MD)
        export_to_html(ordered_master_data, OUTPUT_HTML)
        
        print(f"\n[*] Consolidation Complete! Final database size: {len(ordered_master_data)} rules.")