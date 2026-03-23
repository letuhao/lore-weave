# 🌌 LoreWeave

**The Open Source Creative Home for Novelists.**

LoreWeave is a community-driven project designed to help hobbyist authors, world-builders, and fans of web novels create, translate, and share their stories. It combines the power of AI with the art of storytelling to help you keep your "lore" consistent across every chapter and every language.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-blue.svg)](https://opensource.org/how-to-contribute/)

---

## ✨ Features Built for Storytellers

LoreWeave is more than just a digital notebook—it's an assistant that "understands" your world.

### ✍️ Novel Creation & AI Assistance
Whether you're brainstorming a new plot or polishing dialogue, LoreWeave’s upcoming **Creative Assistant** is being designed to act as your co-author, ensuring every new idea stays true to your established story history.

### 📚 The Lore Weaver (Customizable Glossary) — *Next Milestone*
Never forget a character's detail or a location's history. 
*   **Track Everything**: Create entries for Characters, Locations, Items, and more.
*   **Evidence-Based**: Link your lore entries directly to the specific lines in your chapters.
*   **Highly Customizable**: Add any attribute you need to keep your world-building deep and organized.

### 🌍 Share Your Worlds
Build your novel, translate it for friends around the world, and showcase your universe to a community of like-minded hobbyists.

---

## 🏗️ The LoreWeave Ecosystem (Modules)

LoreWeave is composed of several specialized services working together. This modular "microservices" approach ensures the platform is fast, scalable, and easy to extend.

### 🎨 Frontend & Gateway
| Service | Technology | Role | Port |
| :--- | :--- | :--- | :--- |
| **Frontend** | React + Vite | Premium UI with **Tailwind CSS**. | `5173` |
| **API Gateway (BFF)** | NestJS | Orchestrates all backend requests. | `3000` |

### 🔑 Identity & Foundation
| Service | Technology | Role | Port |
| :--- | :--- | :--- | :--- |
| **Auth Service** | Go (Golang) | Identity and profile management. | `8081` |
| **Mailhog** | SMTP | Local email testing service. | `8025 (UI)` |

### 📖 Narrative & Sharing
| Service | Technology | Role | Port |
| :--- | :--- | :--- | :--- |
| **Book Service** | Go (Golang) | Book and chapter management. | `8082` |
| **Sharing Service** | Go (Golang) | Visibility and ownership permissions. | `8083` |
| **Catalog Service** | Go (Golang) | Public discovery and browsing. | `8084` |

### 🤖 AI & Intelligent Pipelines
| Service | Technology | Role | Port |
| :--- | :--- | :--- | :--- |
| **Provider Registry** | Go (Golang) | Connect your AI keys (BYOK). | `8085` |
| **Usage & Billing** | Go (Golang) | Monitor AI consumption and credits. | `8086` |
| **Translation Service** | Node/TS | Translation job lifecycle management. | `8087` |
| **Translation Worker** | Node/TS | Async job execution via RabbitMQ. | `-` |

### 🗄️ Infrastructure (Engines)
| Engine | Technology | Role | Port |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | Relational DB | The "Source of Truth" for all data. | `5432` |
| **MinIO** | Object Storage | Cloud-native storage for your book files. | `9000` |
| **RabbitMQ** | Message Broker | Handles background and async tasks. | `5672` |

---

## 🤖 Suggested AI Models (BYOK)

LoreWeave is model-agnostic. You can bring your own keys from major cloud providers or host your own local models for total privacy.

### 🌍 For Story Translation
| Focus | Cloud (API) | Self-Hosted (Local) |
| :--- | :--- | :--- |
| **Premium Quality** | **GPT-4o** / **Claude 3.5 Sonnet** | **Llama 3.1 70B** |
| **Budget Friendly** | **DeepSeek-V3** / **DeepSeek-R1** | **Gemma 3 27B** |

### 🧠 For Lore Context (Context Compact)
Fast models used for lore extraction, context distillation, and RAG.
| Focus | Cloud (API) | Self-Hosted (Local) |
| :--- | :--- | :--- |
| **High Speed** | **GPT-4o-mini** / **Claude 3 Haiku** | **Phi-4 Mini** / **Gemma 3 4B** |
| **Deep Reasoning** | **Gemini 1.5 Flash** | **Llama 3.1 8B** |

> [!TIP]
> For **Local Hosting**, we recommend using **[Ollama](https://ollama.com/)** or **[LM Studio](https://lmstudio.ai/)** to expose your models via an OpenAI-compatible API.

---

## 🗺️ Roadmap & Current Situation

The weave is growing fast! We have completed the core functional layers for the basic novel lifecycle.

### 📍 Current Situation: **Phase 1 Foundations (Usable)**
The platform is now **functionally usable** across the core modules:

*   **✅ Identity & Books**: Secure registration and book management are fully active.
*   **✅ Discovery & Sharing**: Books can be shared and browsed in the catalog.
*   **✅ AI Providers**: BYOK registration and usage metering are live.
*   **✅ Raw Translation**: (*Final Stages*) Functional async translation pipeline is live and smoke-tested. 

### 🚀 Upcoming Milestones
- [ ] **UI/UX Polishing** — A dedicated wave to improve the look and feel of the current tools. 
- [ ] **Phase 2: The Lore Weaver** — The advanced, AI-assisted glossary and world-building engine.
- [ ] **Phase 3: Creator Assistance** — Brainstorming and writing tools for authors.

---

## 🛠️ Join the Weave (Local Dev)

Want to help build LoreWeave? You can get the project running in minutes.

### 🐳 The Quickest Start (Docker)
Run the entire platform in one command:
```bash
cd infra
docker compose up --build
```
> Access the UI at: [http://localhost:5173](http://localhost:5173)

### 🛠️ Manual / Hybrid Start
1. **Infra**: `cd infra && docker compose up -d postgres minio rabbitmq mailhog`
2. **Setup**: Copy `.env.example` to `.env` in the services you're working on.
3. **Frontend**: `cd frontend && npm run dev`

---

## 🤝 Contributing & Community

LoreWeave is for everyone. If you're a developer, artist, or author, we'd love for you to join us!

*   **Documentation**: Check out the [docs/](docs/) folder for our architectural plans and designs.
*   **Governance**: We follow a [Contract-First Approach](contracts/) using OpenAPI.
*   **License**: This project is licensed under the **[MIT License](LICENSE)**.

Developed with ❤️ for the Creative Community.
