```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenManus README</title>
</head>
<body>
    <section>
        <h1>👋 OpenManus</h1>
        <p>Manus is incredible, but OpenManus can achieve any idea without an *Invite Code* 🛫!</p>
        <p>Our team members <a href="https://github.com/mannaandpoem">@Xinbin Liang</a> and <a href="https://github.com/XiangJinyu">@Jinyu Xiang</a> (core authors), along with <a href="https://github.com/MoshiQAQ">@Zhaoyang Yu</a>, <a href="https://github.com/didiforgithub">@Jiayi Zhang</a>, and <a href="https://github.com/stellaHSR">@Sirui Hong</a>, we are from <a href="https://github.com/geekan/MetaGPT">@MetaGPT</a>. The prototype is launched within 3 hours and we are keeping building!</p>
        <p>It's a simple implementation, so we welcome any suggestions, contributions, and feedback!</p>
        <p>Enjoy your own agent with OpenManus!</p>
        <p>We're also excited to introduce <a href="https://github.com/OpenManus/OpenManus-RL">OpenManus-RL</a>, an open-source project dedicated to reinforcement learning (RL)- based (such as GRPO) tuning methods for LLM agents, developed collaboratively by researchers from UIUC and OpenManus.</p>
    </section>
    <section>
        <h2>Project Demo</h2>
        <video controls muted style="max-height:640px; min-height: 200px;">
            <source src="https://private-user-images.githubusercontent.com/61239030/420168772-6dcfd0d2-9142-45d9-b74e-d10aa75073c6.mp4?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NDEzMTgwNTksIm5iZiI6MTc0MTMxNzc1OSwicGF0aCI6Ii82MTIzOTAzMC80MjAxNjg3NzItNmRjZmQwZDItOTE0Mi00NWQ5LWI3NGUtZDEwYWE3NTA3M2M2Lm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTAzMDclMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwMzA3VDAzMjIzOVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTdiZjFkNjlmYWNjMmEzOTliM2Y3M2VlYjgyNDRlZDJmOWE3NWZhZjE1MzhiZWY4YmQ3NjdkNTYwYTU5ZDA2MzYmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.UuHQCgWYkh0OQq9qsUWqGsUbhG3i9jcZDAMeHjLt5T4" type="video/mp4">
            Your browser does not support the video tag.
        </video>
    </section>
    <section>
        <h2>Installation</h2>
        <p>We provide two installation methods. Method 2 (using uv) is recommended for faster installation and better dependency management.</p>
        <h3>Method 1: Using conda</h3>
        <pre><code class="bash">
conda create -n open_manus python=3.12
conda activate open_manus
git clone https://github.com/mannaandpoem/OpenManus.git
cd OpenManus
pip install -r requirements.txt
        </code></pre>
        <h3>Method 2: Using uv (Recommended)</h3>
        <pre><code class="bash">
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/mannaandpoem/OpenManus.git
cd OpenManus
uv venv
source .venv/bin/activate  # On Unix/macOS
# Or on Windows:
# .venv\Scripts\activate
uv pip install -r requirements.txt
        </code></pre>
    </section>
    <section>
        <h2>Configuration</h2>
        <p>OpenManus requires configuration for the LLM APIs it uses. Follow these steps to set up your configuration:</p>
        <pre><code class="bash">
cp config/config.example.toml config/config.toml
        </code></pre>
        <pre><code class="toml">
# Global LLM configuration
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."  # Replace with your actual API key
max_tokens = 4096
temperature = 0.0

# Optional configuration for specific LLM models
[llm.vision]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."  # Replace with your actual API key
        </code></pre>
    </section>
    <section>
        <h2>Quick Start</h2>
        <pre><code class="bash">
python main.py
        </code></pre>
        <p>Then input your idea via terminal!</p>
        <p>For unstable version, you also can run:</p>
        <pre><code class="bash">
python run_flow.py
        </code></pre>
    </section>
    <section>
        <h2>How to contribute</h2>
        <p>We welcome any friendly suggestions and helpful contributions! Just create issues or submit pull requests.</p>
        <p>Or contact @mannaandpoem via 📧email: mannaandpoem@gmail.com</p>
    </section>
    <section>
        <h2>Community Group</h2>
        <p>Join our networking group on Feishu and share your experience with other developers!</p>
        <div style="display: flex; justify-content: center;">
            <img src="assets/community_group.jpg" alt="OpenManus 交流群" width="300" />
        </div>
    </section>
    <section>
        <h2>Star History</h2>
        <img src="https://api.star-history.com/svg?repos=mannaandpoem/OpenManus&type=Date" alt="Star History Chart">
    </section>
    <section>
        <h2>Acknowledgement</h2>
        <p>Thanks to <a href="https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo">anthropic-computer-use</a> and <a href="https://github.com/browser-use/browser-use">browser-use</a> for providing basic support for this project!</p>
        <p>Additionally, we are grateful to <a href="https://github.com/metauto-ai/agent-as-a-judge">AAAJ</a>, <a href="https://github.com/geekan/MetaGPT">MetaGPT</a> and <a href="https://github.com/All-Hands-AI/OpenHands">OpenHands</a>.</p>
        <p>OpenManus is built by contributors from MetaGPT. Huge thanks to this agent community!</p>
    </section>
    <section>
        <h2>Cite</h2>
        <pre><code class="bibtex">
@misc{openmanus2025,
  author = {Xinbin Liang and Jinyu Xiang and Zhaoyang Yu and Jiayi Zhang and Sirui Hong},
  title = {OpenManus: An open-source framework for building general AI agents},
  year = {2025},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/mannaandpoem/OpenManus}},
}
        </code></pre>
    </section>
</body>
</html>
```
