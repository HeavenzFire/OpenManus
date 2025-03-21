

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Interactive Display</title>
    <style>
        :root {
            --primary: #1abc9c;
            --secondary: #2c3e50;
            --accent: #f1c40f;
            --text: #ecf0f1;
        }

        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, var(--secondary) 0%, #34495e 100%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .container {
            background: rgba(52, 73, 94, 0.9);
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 1rem 2rem rgba(0, 0, 0, 0.3);
            width: 90%;
            max-width: 600px;
            backdrop-filter: blur(10px);
        }

        h1 {
            color: var(--primary);
            text-align: center;
            margin-bottom: 1.5rem;
            font-size: 2.2rem;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        .capability-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .capability-card {
            background: rgba(41, 128, 185, 0.15);
            padding: 1.5rem;
            border-radius: 0.5rem;
            transition: all 0.3s ease;
            cursor: pointer;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .capability-card:hover {
            transform: translateY(-5px);
            background: rgba(41, 128, 185, 0.25);
            box-shadow: 0 8px 15px rgba(0, 0, 0, 0.2);
        }

        .input-group {
            position: relative;
            margin-top: 1.5rem;
        }

        input[type="text"] {
            width: 100%;
            padding: 1rem;
            border: 2px solid var(--primary);
            border-radius: 0.5rem;
            background: rgba(255, 255, 255, 0.1);
            color: var(--text);
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 15px rgba(241, 196, 15, 0.3);
        }

        button {
            background: var(--primary);
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
            width: 100%;
            margin-top: 1rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        button:hover {
            background: #16a085;
            transform: translateY(-2px);
        }

        .response-container {
            margin-top: 2rem;
            padding: 1.5rem;
            background: rgba(39, 174, 96, 0.15);
            border-radius: 0.5rem;
            border: 1px solid rgba(39, 174, 96, 0.3);
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.4s ease;
        }

        .response-container.visible {
            opacity: 1;
            transform: translateY(0);
        }

        @media (max-width: 480px) {
            .container {
                padding: 1.5rem;
            }
            
            h1 {
                font-size: 1.8rem;
            }
        }

        .loading {
            display: none;
            text-align: center;
            margin: 1rem 0;
        }

        .loading-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            margin: 0 3px;
            background: var(--primary);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }

        @keyframes bounce {
            0%, 80%, 100% { transform: translateY(0); }
            40% { transform: translateY(-10px); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Interaction Portal</h1>
        
        <div class="capability-list">
            <div class="capability-card">
                <h3>🧠 Quantum Computing</h3>
                <p>Understand quantum principles through interactive simulations</p>
            </div>
            <div class="capability-card">
                <h3>💻 Code Generation</h3>
                <p>Generate code snippets in multiple programming languages</p>
            </div>
            <div class="capability-card">
                <h3>📊 Data Insights</h3>
                <p>Visualize complex datasets with intelligent analysis</p>
            </div>
        </div>

        <div class="input-group">
            <input type="text" id="userInput" placeholder="Ask me anything...">
            <button onclick="processQuery()">Get Insight</button>
            <div class="loading" id="loading">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
            </div>
        </div>

        <div class="response-container" id="response"></div>
    </div>

    <script>
        const capabilities = {
            quantum: {
                response: "Quantum computing leverages quantum bits (qubits) that can exist in superposition. This means they can represent both 0 and 1 simultaneously, enabling parallel processing capabilities far beyond classical computers.",
                example: "For instance, Shor's algorithm can factor large numbers exponentially faster than classical algorithms, potentially revolutionizing cryptography."
            },
            code: {
                response: "Here's a Python example of a quantum circuit simulation using Qiskit:",
                example: `from qiskit import QuantumCircuit, transpile
qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()`
            },
            data: {
                response: "Advanced data analysis might involve machine learning techniques like:",
                example: "- Random Forests for classification\n- PCA for dimensionality reduction\n- LSTM networks for time series prediction"
            }
        };

        function showLoading(show) {
            document.getElementById('loading').style.display = show ? 'block' : 'none';
        }

        function animateResponse() {
            const responseDiv = document.getElementById('response');
            responseDiv.classList.add('visible');
        }

        async function processQuery() {
            const input = document.getElementById('userInput').value.trim();
            const responseDiv = document.getElementById('response');
            
            if (!input) {
                responseDiv.innerHTML = "Please enter a valid query";
                animateResponse();
                return;
            }

            showLoading(true);
            responseDiv.classList.remove('visible');

            // Simulated API call delay
            await new Promise(resolve => setTimeout(resolve, 800));

            let responseContent = "";
            const inputLower = input.toLowerCase();

            if (inputLower.includes('quantum')) {
                responseContent = `
                    <h4>${capabilities.quantum.response}</h4>
                    <p>${capabilities.quantum.example}</p>
                `;
            } else if (inputLower.includes('code')) {
                responseContent = `
                    <h4>${capabilities.code.response}</h4>
                    <pre>${capabilities.code.example}</pre>
                `;
            } else if (inputLower.includes('data')) {
                responseContent = `
                    <h4>${capabilities.data.response}</h4>
                    <pre>${capabilities.data.example}</pre>
                `;
            } else {
                responseContent = `
                    <h4>Advanced Response:</h4>
                    <p>${input} - This is a simulated response showing the system's capability to handle complex queries. 
                    In a real implementation, this would connect to an AI API for dynamic responses.</p>
                `;
            }

            responseDiv.innerHTML = responseContent;
            showLoading(false);
            animateResponse();
            document.getElementById('userInput').value = "";
        }

        // Add keyboard support
        document.getElementById('userInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') processQuery();
        });
    </script>
</body>
</html>
```

Key improvements made:

1. Modern Design System:
- CSS variables for consistent theming
- Gradient background with glassmorphism effects
- Responsive grid layout for capability cards
- Smooth animations and transitions

2. Enhanced Features:
- Card-based capability display with hover effects
- Loading animation during processing
- Better keyboard accessibility (Enter key support)
- Organized response templates
- Proper code formatting in responses

3. Technical Improvements:
- CSS Grid for responsive layout
- Modern CSS features (backdrop-filter, CSS variables)
- Better mobile responsiveness
- Async/await pattern for simulated API calls
- Cleaner JavaScript organization

4. Visual Enhancements:
- Icon integration in card headers
- Pre-formatted code blocks
- Improved typography and spacing
- Animated response container
- Interactive hover states

To use this enhanced version:
1. Enter queries related to:
   - Quantum computing
   - Code generation
   - Data analysis
2. Click the button or press Enter
3. View formatted responses with code examples
4. Explore the interactive capability cards

The system can be further enhanced by connecting it to an actual AI API backend for real-time responses instead of the simulated ones.
