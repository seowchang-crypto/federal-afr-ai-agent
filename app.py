import streamlit as st
import pandas as pd
import os
import tempfile

# =====================================================================
# 1. IMPORT YOUR BACKEND SCRIPTS
# =====================================================================
try:
    from convert_pdf_to_md import process_pdf_in_chunks 
    from AFR_reviewer import run_afr_review 
except ImportError:
    st.error("Backend scripts not found.")

# =====================================================================
# 2. Page Configuration & Banners
# =====================================================================
st.set_page_config(
    page_title="Agency Financial Report AI Disclosure Reviewer",
    page_icon="📊",
    layout="wide"
)

st.info("🚧 **BETA VERSION:** This tool is currently in active development. We welcome your feedback and suggestions to help us improve its accuracy and workflow. Please send feedback to the development team.")

st.warning("""
**⚠️ REGULATORY DISCLAIMER & TERMS OF USE:** This AI-assisted tool is designed exclusively to accelerate the review process. It does **not** replace professional judgment. 

The final responsibility for ensuring that the Federal Agency Financial Report (AFR) complies with OMB A-136, SFFAS, and all other regulatory requirements rests **solely with the preparer and the auditor**. The developers and this AI tool are not liable for any misjudgments, omissions, compliance failures, or factual inaccuracies.
""")

st.title("Federal Agency Financial Report (AFR) Reviewer")
st.markdown("Upload your draft AFR below to run an automated presentation and disclosure compliance check against the Comprehensive Disclosure Checklist.")

# =====================================================================
# 3. The Uploader & Execution Logic
# =====================================================================
uploaded_file = st.file_uploader("Upload Draft AFR", type=['pdf', 'docx', 'md'])

if uploaded_file is not None:
    st.success(f"File '{uploaded_file.name}' uploaded successfully!")
    
    if st.button("Run Automated Review", type="primary"):
        
        # Create a temporary directory to store files during processing
        # This automatically cleans up after the script finishes
        with tempfile.TemporaryDirectory() as temp_dir:
            
            # Save the uploaded file physically to the temp directory
            input_file_path = os.path.join(temp_dir, uploaded_file.name)
            with open(input_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            # Determine file extension
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            md_file_path = input_file_path # Default assumption
            
            # --- STEP A: CONVERSION ROUTING ---
            if file_ext != '.md':
                st.info(f"🔄 Non-Markdown file detected ({file_ext}). Initiating conversion to Markdown...")
                md_file_path = os.path.join(temp_dir, "converted_afr.md")
                
                with st.spinner("Converting document via Azure... Check your terminal for chunk progress."):
                    try:
                        # Call your isolated multiprocessing function
                        process_pdf_in_chunks(input_file_path, md_file_path, chunk_size=30)
                        st.success("✅ Conversion complete!")
                    except Exception as e:
                        st.error(f"❌ Conversion failed: {e}")
                        st.stop()
            else:
                st.info("✅ Markdown file detected. Bypassing conversion.")

            # --- STEP B: AI REVIEW ROUTING ---
            st.info("🧠 Running AI AFR Compliance Review...")
            with st.spinner("Analyzing disclosures against OMB A-136 & SFFAS..."):
                try:
                    # CALL YOUR REVIEWER HERE (Expecting a Pandas DataFrame back)
                    results_df = run_afr_review(md_file_path)
                    st.success("✅ Review complete!")
                except Exception as e:
                    st.error(f"❌ Review failed: {e}")
                    st.stop()

            # =====================================================================
            # 4. Displaying the Real Results
            # =====================================================================
            st.subheader("Review Results")
            
            if results_df is not None and not results_df.empty:
                st.dataframe(
                    results_df, 
                    use_container_width=True,
                    hide_index=True
                )
                
                # =====================================================================
                # 5. Export Hub
                # =====================================================================
                st.markdown("### Export Findings")
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📥 Download CSV Workpaper",
                        data=results_df.to_csv(index=False),
                        file_name="AFR_Review_Results.csv",
                        mime="text/csv"
                    )
                with col2:
                    st.button("📄 Open HTML Management Dashboard (Pending Integration)")
            else:
                st.warning("The review completed, but no results were returned.")