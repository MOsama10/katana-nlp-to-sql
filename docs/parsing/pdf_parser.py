import pdfplumber
import json
import os
import re

# Patterns to clean unwanted text
REMOVE_PATTERNS = [
    r"All rights reserved\s*\|\s*(Digis2\.com|www\.DigisSquared\.com).*",
    r"Page\s*\d+",
    r"=====\s*Page \d+\s*=====",
    r"^\s*$",
    r"digis[\'®]?",
    r"Last data update: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
    r"KATANA\s*$",
    r"^[\-\*]+\s*$",
    r"^\s*[\*\-\#]+\s*$",
    r"^[\d\.]+\s*$"
]

# Section headings for grouping
SECTION_TITLES = [
    "What is Private Network", "Private Network", "Private Networks", 
    "Private network deployment models", "SNPN", "PNI-NPN", 
    "Standalone Non-Public Network", "Public Network Integrated",
    "Private Network implementation example", "ORAN",

    "KATANA PLATFORM APPLICATIONS", "KATANA Platform", "KATANA",
    "PRODUCT PHILOSOPHY", "CHALLENGES - VALUE PROPOSITION", 
    "KATANA as an AIOps enabler", "KATANA USE CASES", "KEY ADVANTAGES",
    "PLATFORM APPLICATIONS", "Main Product Modules",

    "IPM MODULES", "iPM Performance Management", "UFM MODULES", 
    "UFM Faults Management", "NetEye Module", "NetEye Configuration Management",
    "Parameter Browser", "Activity Log", "Topology Viewer",

    "INOS PLATFORM APPLICATIONS", "INOS Platform", "CBTP", "NXI", "ARP",
    "Octomind", "Connectsphere", "In&Kits",

    "Deployment Models", "USE CASES", "AI based", "Modules", "KPIs", 
    "Performance", "SOC", "Dashboards", "Site Activation", "Topology",
    "Network Slicing", "RAN", "Core", "5G", "LTE", "Cloud Native",

    "SUPPORTED TECHNOLOGIES", "KEY BENEFITS", "Dashboard Flexibility",
    "Flexible Dashboards", "OUR PRESENCE & KEY CUSTOMERS", "Thank you"
]

def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        skip = False
        for pattern in REMOVE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                skip = True
                break
        if not skip:
            cleaned_lines.append(line.strip())
    return '\n'.join(cleaned_lines).strip()

def split_into_sections(pages):
    sections = {}
    current_section = "General"
    sections[current_section] = ""

    for page in pages:
        lines = page['text'].split('\n')
        for line in lines:
            clean_line = line.strip()
            if any(title.lower() in clean_line.lower() for title in SECTION_TITLES):
                current_section = clean_line
                if current_section not in sections:
                    sections[current_section] = ""
            sections[current_section] += clean_line + "\n"
    
    return sections

def parse_pdf_to_prompt_response(pdf_path, output_path):
    pages_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            raw_text = page.extract_text()
            if raw_text:
                cleaned = clean_text(raw_text)
                pages_text.append({
                    "page": i + 1,
                    "text": cleaned
                })

    sections = split_into_sections(pages_text)

    training_dataset = []
    for section_title, section_text in sections.items():
        prompt = f"What is covered in the section: {section_title}?"
        response = section_text.strip()
        if len(response.split()) > 5:
            training_dataset.append({
                "prompt": prompt,
                "response": response
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(training_dataset, f, indent=2, ensure_ascii=False)

    print(f"✅ Training dataset saved to {output_path} with {len(training_dataset)} entries.")

if __name__ == "__main__":
    pdf_path = r"E:\digis task\Task\katana_nlp_to_sql\docs\Products & Services Overview.pdf"
    output_path = r"E:\digis task\Task\katana_nlp_to_sql\docs\training_data\parsed_content.json"
    parse_pdf_to_prompt_response(pdf_path, output_path)
