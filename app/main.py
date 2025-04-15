from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.api.query_router import router
import time
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Katana AI Platform",
    description="Natural language to SQL interface for telecommunications network analytics",
    version="1.0.0",
    # Add some optimized settings
    docs_url="/docs",
    redoc_url=None,  # Disable ReDoc to save resources
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timing middleware with early return for health checks
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    # Skip processing for health checks
    if request.url.path == "/health":
        return await call_next(request)
        
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Include router
app.include_router(router, prefix="/api")

# Mount static files if directory exists
static_dir = os.path.abspath("static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Return a simple web interface for querying the Katana platform."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Katana AI Platform</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f5f5;
                color: #333;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
            }
            h1 {
                color: #0f4c81;
                text-align: center;
            }
            .query-box {
                margin: 30px 0;
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            input[type=text] {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
                font-size: 16px;
            }
            button {
                background-color: #0f4c81;
                color: white;
                border: none;
                padding: 12px 20px;
                margin-top: 10px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
            }
            button:hover {
                background-color: #0a3b66;
            }
            .result-box {
                margin-top: 20px;
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                display: none;
            }
            .sql-query {
                background-color: #f0f0f0;
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
                font-family: monospace;
                white-space: pre-wrap;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            th, td {
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f2f2f2;
            }
            .error {
                color: #d32f2f;
                padding: 10px;
                background-color: #ffebee;
                border-radius: 4px;
            }
            .loader {
                border: 5px solid #f3f3f3;
                border-top: 5px solid #0f4c81;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 2s linear infinite;
                margin: 20px auto;
                display: none;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Katana AI Platform</h1>
            <p>Ask questions about your telecommunications network data in natural language.</p>
            
            <div class="query-box">
                <h2>Enter your query</h2>
                <p>Example queries:</p>
                <ul>
                    <li>What objects do we have in the system?</li>
                    <li>What counters are available for LTE_MAC objects?</li>
                    <li>What vendors does the platform support?</li>
                </ul>
                <input type="text" id="query-input" placeholder="Type your question here...">
                <button onclick="executeQuery()">Run Query</button>
                <div class="loader" id="loader"></div>
            </div>
            
            <div class="result-box" id="result-box">
                <h2>Results</h2>
                <h3>SQL Query:</h3>
                <div class="sql-query" id="sql-query"></div>
                <div id="error-box" class="error" style="display:none;"></div>
                <div id="table-container"></div>
            </div>
        </div>
        
        <script>
            function executeQuery() {
                const query = document.getElementById('query-input').value;
                if (!query) return;
                
                document.getElementById('loader').style.display = 'block';
                document.getElementById('result-box').style.display = 'none';
                document.getElementById('error-box').style.display = 'none';
                
                fetch(`/api/query?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('loader').style.display = 'none';
                        document.getElementById('result-box').style.display = 'block';
                        document.getElementById('sql-query').textContent = data.sql;
                        
                        if (data.error) {
                            document.getElementById('error-box').style.display = 'block';
                            document.getElementById('error-box').textContent = `Error: ${data.error}`;
                            if (data.suggestion) {
                                document.getElementById('error-box').textContent += `\nSuggestion: ${data.suggestion}`;
                            }
                            document.getElementById('table-container').innerHTML = '';
                        } else {
                            const results = data.results;
                            if (results && results.length > 0) {
                                // Create table
                                let tableHtml = '<table><thead><tr>';
                                const headers = Object.keys(results[0]);
                                headers.forEach(header => {
                                    tableHtml += `<th>${header}</th>`;
                                });
                                tableHtml += '</tr></thead><tbody>';
                                
                                results.forEach(row => {
                                    tableHtml += '<tr>';
                                    headers.forEach(key => {
                                        tableHtml += `<td>${row[key] !== null ? row[key] : 'NULL'}</td>`;
                                    });
                                    tableHtml += '</tr>';
                                });
                                
                                tableHtml += '</tbody></table>';
                                document.getElementById('table-container').innerHTML = tableHtml;
                            } else {
                                document.getElementById('table-container').innerHTML = '<p>No results found.</p>';
                            }
                        }
                    })
                    .catch(error => {
                        document.getElementById('loader').style.display = 'none';
                        document.getElementById('result-box').style.display = 'block';
                        document.getElementById('error-box').style.display = 'block';
                        document.getElementById('error-box').textContent = `Error: ${error.message}`;
                        document.getElementById('table-container').innerHTML = '';
                    });
            }
            
            // Execute query when pressing Enter
            document.getElementById('query-input').addEventListener('keypress', function(event) {
                if (event.key === 'Enter') {
                    executeQuery();
                }
            });
        </script>
    </body>
    </html>
    """

@app.get("/health")
async def health_check():
    """Simplified health check endpoint."""
    return {"status": "healthy"}
