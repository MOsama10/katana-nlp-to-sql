Here’s a polished and concise version of your `README.md` for GitHub:

---

# Katana NLP-to-SQL Platform  

A **CPU-optimized** natural language to SQL (NLP-to-SQL) pipeline for the **Katana** telecom analytics platform, enabling non-technical users to query PostgreSQL data using plain English. Built with FastAPI, PostgreSQL, and SQLCoder (GGUF) via `llama.cpp` for fully offline inference.  

---

## ✨ Features  
- Converts natural language to PostgreSQL queries  
- Leverages domain knowledge from Katana’s documentation  
- Dynamically loads database schema  
- Local CPU-only inference (no GPU/API dependencies)  
- Pre-trained logic for objects, counters, and time-based queries  

---

## 🛠️ Installation  

1. **Clone the repository**  
   ```bash  
   git clone https://github.com/MOsama10/katana-nlp-to-sql.git  
   cd katana-nlp-to-sql  
   ```  

2. **Set up a virtual environment**  
   ```bash  
   python -m venv katana_env  
   source katana_env/bin/activate  # Linux/Mac  
   katana_env\Scripts\activate    # Windows  
   pip install -r requirements.txt  
   ```  

3. **Configure PostgreSQL**  
   - Update `.env` with your database credentials:  
     ```dotenv  
     DB_NAME=katana_db  
     DB_USER=postgres  
     DB_PASSWORD=yourpassword  
     DB_HOST=localhost  
     DB_PORT=5432  
     ```  
   - Import CSV data:  
     ```bash  
     python database/import_csv.py  
     ```  

4. **Run the FastAPI server**  
   ```bash  
   uvicorn app.main:app --reload  
   ```  
   Access the Swagger UI at: `http://127.0.0.1:8000/docs`  

---

## 📂 Project Structure  
```  
katana_nlp_to_sql/  
├── app/              # FastAPI backend  
├── database/         # PostgreSQL scripts  
├── docs/             # Parsed Katana documentation  
├── model/            # NLP-to-SQL logic  
├── models/           # SQLCoder GGUF model  
└── requirements.txt  
```  

---

## 💡 Example Queries  
**System Exploration:**  
- *“What families do we have in the system?”*  
- *“What objects do we have in our system?”*  
- *“What objects does Katana cover?”*  
- *“What vendors does Katana support?”*  

**Counter Analysis:**  
- *“List counters for object 3G.”*  
- *“What is the list of counters covered for object 3G?”*  
---

The model enforces:  
✅ Schema-aware SQL generation  
✅ Fuzzy matching via `ILIKE`  
✅ No hallucinations (strict table/column validation)  

---

## 📜 License  
Private to [MOsama10](mailto:M.Osama10@gmail.com). Katana-related content is property of Digis.  

---

## 🔍 Support  
Open a GitHub issue or contact [MOsama10](mailto:M.Osama10@gmail.com).  

--- 
