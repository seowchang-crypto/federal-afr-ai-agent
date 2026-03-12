import os
import argparse
import time
import multiprocessing
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from pypdf import PdfReader, PdfWriter

load_dotenv()

ENDPOINT = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
API_KEY = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")

def worker_process(chunk_index, start_page, end_page, input_path, chunk_md_file, figures_dir, base_name):
    """
    This function runs in a completely isolated memory space.
    When it finishes, the operating system instantly reclaims all its RAM.
    """
    # 1. Init a fresh Azure Client just for this isolated process
    client = DocumentIntelligenceClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    
    # 2. Read only the specific pages we need
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page_num in range(start_page, end_page):
        writer.add_page(reader.pages[page_num])
        
    chunk_pdf_file = f"{chunk_md_file}.pdf"
    with open(chunk_pdf_file, "wb") as f_out:
        writer.write(f_out)
        
    # 3. Azure Extraction
    try:
        with open(chunk_pdf_file, "rb") as f_in:
            poller = client.begin_analyze_document(
                model_id="prebuilt-layout", 
                body=f_in, 
                output_content_format="markdown", 
                content_type="application/octet-stream"
            )
        result = poller.result()
        operation_id = poller.details.get("operation_id")
        md_content = result.content
        
        # 4. Download Figures
        if result.figures and operation_id:
            for figure in result.figures:
                if figure.id:
                    response = client.get_analyze_result_figure(
                        model_id="prebuilt-layout", result_id=operation_id, figure_id=figure.id
                    )
                    fig_filename = f"chunk_{chunk_index}_{figure.id}.png"
                    fig_path = os.path.join(figures_dir, fig_filename)
                    
                    with open(fig_path, "wb") as writer_fig:
                        for c in response:
                            writer_fig.write(c)
                            
                    markdown_img_link = f"\n\n![{fig_filename}]({base_name}_figures/{fig_filename})\n\n"
                    placeholder = f""
                    
                    if placeholder in md_content:
                        md_content = md_content.replace(placeholder, markdown_img_link)
                    else:
                        md_content += markdown_img_link
                        
        # 5. Save and Clean up
        with open(chunk_md_file, "w", encoding="utf-8") as f_md:
            f_md.write(md_content)
            
        if os.path.exists(chunk_pdf_file):
            os.remove(chunk_pdf_file)
            
    except Exception as e:
        print(f"[!] Azure API Error on chunk {chunk_index + 1}: {e}")
        if os.path.exists(chunk_pdf_file):
            os.remove(chunk_pdf_file)
        raise e # Pass the error up to the manager so it knows to stop

def process_pdf_in_chunks(input_path, output_path, chunk_size=30):
    if not ENDPOINT or not API_KEY:
        print("[!] ERROR: Azure credentials not found in .env file.")
        return

    if not os.path.exists(input_path):
        print(f"[!] ERROR: Input file '{input_path}' not found.")
        return

    out_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else "."
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    figures_dir = os.path.join(out_dir, f"{base_name}_figures")
    temp_dir = os.path.join(out_dir, f"{base_name}_temp_chunks")
    
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    print(f"[*] Reading '{input_path}' to map pages...")
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    
    chunks = []
    for start_page in range(0, total_pages, chunk_size):
        end_page = min(start_page + chunk_size, total_pages)
        chunks.append((start_page, end_page))
        
    print(f"[*] Splitting PDF into {len(chunks)} chunks of up to {chunk_size} pages each.")
    print(f"[*] MEMORY ISOLATION ENABLED: Spawning child processes for zero-leak processing.")
    
    for i, (start, end) in enumerate(chunks):
        chunk_md_file = os.path.join(temp_dir, f"chunk_{i}.md")
        
        if os.path.exists(chunk_md_file):
            print(f"  -> Skipping Chunk {i+1}/{len(chunks)} (Pages {start+1}-{end}) - Already processed.")
            continue
            
        print(f"  -> Spawning isolated process for Chunk {i+1}/{len(chunks)} (Pages {start+1}-{end})...")
        
        # Spawn the isolated worker
        p = multiprocessing.Process(
            target=worker_process, 
            args=(i, start, end, input_path, chunk_md_file, figures_dir, base_name)
        )
        p.start()
        p.join() # Wait for the worker to finish and self-destruct
        
        if p.exitcode != 0:
            print("[!] Worker process failed. Stopping safely. Rerun to resume.")
            return
            
        time.sleep(2) # Polite API rate limiting

    print(f"\n[*] All chunks processed. Stitching final Markdown document...")
    with open(output_path, "w", encoding="utf-8") as final_file:
        for i in range(len(chunks)):
            chunk_md_file = os.path.join(temp_dir, f"chunk_{i}.md")
            if os.path.exists(chunk_md_file):
                with open(chunk_md_file, "r", encoding="utf-8") as piece:
                    final_file.write(piece.read() + "\n\n")
                    
    print(f"[+] Success! Final Markdown saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert massive PDFs with Process Isolation")
    parser.add_argument("-i", "--input", required=True, help="Path to the input PDF")
    parser.add_argument("-o", "--output", required=True, help="Path for the output Markdown file")
    
    args = parser.parse_args()
    
    # You can safely increase this to 30+ without fear of memory leaks
    process_pdf_in_chunks(args.input, args.output, chunk_size=30)