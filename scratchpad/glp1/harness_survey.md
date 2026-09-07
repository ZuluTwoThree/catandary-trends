# Deep-Research-Harnesses: Survey (Stand 2026-09-07)

Geprüft: die 11 genannten Kandidaten plus WebWeaver/ReSum (Tongyi-Familie), LearningCircuit/local-deep-research, langchain-ai/local-deep-researcher, HKUDS/AutoAgent, federicodeponte/opendraft.

## 1. Repos

### stanford-oval/storm (STORM + Co-STORM) — MIT
https://github.com/stanford-oval/storm
- Zweck: „writes Wikipedia-like articles from scratch based on Internet search". Stufen: Knowledge Curation → Outline Generation → Article Generation → Article Polishing.
- Suchanfragen (`storm_wiki/modules/persona_generator.py`): FindRelatedTopic („identify and recommend some Wikipedia pages on closely related subjects") → Inhaltsverzeichnisse (h2–h6) der Nachbarseiten → GenPersona („Wikipedia editors … each representing a different perspective, role, or affiliation"), Default „Basic fact writer", max 3+1. `knowledge_curation.py`: je Persona simulierte Konversation (max_turn): AskQuestionWithPersona → QuestionToQuery („What do you type in the search box?") → AnswerQuestion („every sentence is supported by the gathered information", 1000 Wörter Kappe); Ende bei „Thank you so much for your help!".
- Belege (`storm_dataclass.py`): StormInformationTable, url_to_info mit Snippet-Merge, `retrieve_information(queries, search_top_k)` per Cosine über SentenceTransformer-Embeddings — kein Vektorstore. Outline: Draft aus Topic, Refinement aus der Konversation (5000 Wörter Kappe).
- Bericht: je Erstlevel-Abschnitt Retrieval mit der Abschnitts-Outline als Query, WriteSection mit „[1][3]"-Zitaten und 1500 Wörtern Kontext; Zitatindizes in `_merge_new_info_to_references` vereinheitlicht. Polish: PolishPage („You won't delete any non-repeated part … keep the inline citations and article structure"). Co-STORM (arXiv 2408.15232): Moderator rerankt Funde „based on the similarity to the topic and the dissimilarity to its associated question" — unbenutzte Treffer werden neue Fragen; Mind-Map-Knoten halten Zitatindex-Mengen, Bericht abschnittsweise (4000 Wörter je Knoten). `run_storm_wiki_ollama.py` vorhanden; litellm-Backends.

### Future-House/paper-qa (PaperQA2) — Apache-2.0
https://github.com/Future-House/paper-qa
- Zweck: „high-accuracy RAG … with a focus on the scientific literature".
- Stufen (Agent wählt Tools): paper_search („LLM-generated keyword query") → gather_evidence („Rank top k document chunks", „Create scored summary of each chunk in the context of the current query", „Use LLM to re-score") → gen_answer. Paper (arXiv 2409.13740): zusätzlich „citation traversal" über den Zitationsgraphen (nicht im OSS-Stand).
- Belege (`src/paperqa/prompts.py`): „Summarize the excerpt … Do not directly answer the question, instead summarize to give evidence"; JSON {summary, relevance_score 0–10}; evidence_k=10, answer_max_sources=5, „about 100 words". Antwort: „If the context provides insufficient information reply 'I cannot answer.' … indicate which sources most support it via citation keys".
- Lokal: Ollama/llamafile/vLLM via litellm, aber „You won't get good performance with 7B models".

### langchain-ai/open_deep_research — MIT
https://github.com/langchain-ai/open_deep_research
- Stufen (`src/open_deep_research/deep_researcher.py`): clarify_with_user → write_research_brief („Fill in Unstated But Necessary Dimensions as Open-Ended") → supervisor (Tools ConductResearch/ResearchComplete/think_tool; „Bias towards single agent", „Comparisons … a sub-agent for each element", „Always stop after {max_researcher_iterations} tool calls") → researcher (Stoppregeln, 2–5 Suchen) → compress_research → final_report_generation.
- Verdichtung (`prompts.py`): Webseiten auf „25-30 percent" + ≤5 key_excerpts; compress_research: „All relevant information should be repeated and rewritten verbatim, but in a cleaner format", „include ALL of the sources", Nummern „without gaps"; bei Token-Limit `remove_up_to_last_ai_message`, Findings auf `model_token_limit*4` gekappt.
- Bericht: ein Durchgang aus `notes`, Struktur frei. Modelle müssen „support structured outputs and tool calling". Legacy (`src/legacy/graph.py`): Plan mit Sections (Name/Description/Research-Flag) → Human-Feedback → je Abschnitt generate_queries → search_web → write_section → Feedback{grade pass/fail, follow_up_queries} bis max_search_depth → Intro/Conclusion ohne Recherche.

### assafelovic/gpt-researcher — Apache-2.0
https://github.com/assafelovic/gpt-researcher
- Stufen: Agent-Rolle nach Thema → Sub-Queries („Write {n} search queries to research the following task", keine Operatoren) → Scrapen je Query → Kompression (`context/compression.py`: 1000-Zeichen-Chunks, EmbeddingsFilter 0.35, max_results 5) → Bericht („at least {total_words} words", Hyperlink-Zitate).
- Detailed Report (`backend/report_type/detailed_report/detailed_report.py`): Hauptrecherche → get_subtopics → je Subtopic eigener Researcher, write_report mit existing_headers + relevant_written_contents („Prevent any content that is already covered") → Intro, TOC, Conclusion, Referenzen. Deep Research (`skills/deep_research.py`): Queries mit researchGoal, „Learning [source_url]: <insight>", Follow-ups, breadth halbiert je Ebene. `curate_sources`: „Prioritize sources with statistics … DO NOT rewrite, summarize, or condense". OpenAI-kompatible Endpoints; Retriever u. a. Brave, arXiv, PubMed.

### Alibaba-NLP/DeepResearch (Tongyi) + WebWeaver/ReSum — Apache-2.0
https://github.com/Alibaba-NLP/DeepResearch
- Modell 30.5B-A3B (offene Gewichte), 128K; Modi ReAct und „Heavy". Paper (arXiv 2510.24701, 2509.13309): Zustand je Runde = „the question q, an evolving report St serving as compressed memory, and the immediate context from the last interaction"; Ausgabe Think/Report/Action gegen „cognitive workspace suffocation" und „irreversible noise contamination". Heavy: n Agenten → je ein Bericht → Synthesis.
- WebWeaver (arXiv 2509.13312): Planner pflegt Outline + Memory Bank und „populates the outline with citations, mapping each section to the specific evidence IDs in the memory bank"; Writer holt je Abschnitt nur zitierte Evidenz, danach „explicitly pruned from the context window and replaced with a placeholder"; Zitatgenauigkeit 93.37 %; SFT (WebWeaver-3k) hebt Qwen3-30b von 25 auf 85.9 %. ReSum (arXiv 2509.13313): Summary-Tool kondensiert den Verlauf, „4.5% improvement over ReAct in training-free settings".

### bytedance/deer-flow v1 (Branch `main-1.x`) — MIT
https://github.com/bytedance/deer-flow/tree/main-1.x
- Stufen: Coordinator → Background Investigation → Planner → Research Team (Researcher/Coder) → Reporter; Plan-Review mit max_plan_iterations.
- Planner (`src/prompts/planner.md`): `has_enough_context` nur, wenn „Current information fully answers ALL aspects … with specific details"; „Analysis Framework" mit acht Achsen: Historical Context, Current State, Future Indicators, Stakeholder Data, Quantitative, Qualitative, Comparative, Risk Data; Steps mit need_search/step_type research|analysis|processing als JSON.
- Reporter (`reporter.md`): Title, Key Points, Overview, Detailed Analysis, Key Citations; „Only use information explicitly provided", „state 'Information not provided'", „Do not include inline citations in the text", „PRIORITIZE USING MARKDOWN TABLES". Modelle „must support tool calling or structured output". v2 (`main`) ist ein Neubau („shares no code with v1"), Modelle „must declare support for tool-calling".

### jina-ai/node-DeepResearch — Apache-2.0
https://github.com/jina-ai/node-DeepResearch · https://jina.ai/news/a-practical-guide-to-implementing-deepsearch-deepresearch/
- Loop search/visit/reflect/answer bis Token-Budget; Gap-Fragen als FIFO, Originalfrage stets hinten; Prompt je Schritt mit `<knowledge>`, `<context>`, `<bad-attempts>`; „Beast Mode" bei Budgetende.
- Suchanfragen (`src/tools/query-rewriter.ts`): genau 7 Queries aus 7 Personas — Expert Skeptic, Detail Analyst, Historical Researcher, Comparative Thinker, Temporal Context, Globalizer, Reality-Hater-Skepticalist.
- Prüfung (`src/tools/evaluator.ts`): definitive / freshness / plurality / completeness / strict; „Answer generation and evaluation should not be in the same prompt". Langbericht: TOC → DeepSearch je Abschnitt → „a single coherence revision pass is sufficient". Braucht Output „following JSONSchema", „reasoning model is likely needed".

### dzhng/deep-research — MIT
https://github.com/dzhng/deep-research
- „<500 LoC". generateSerpQueries (3, mit researchGoal) → processSerpResult: „learnings should be concise … include any entities like people, places, companies, products … exact metrics, numbers, or dates", 3 Learnings + 3 Follow-ups → Rekursion (breadth halbiert) → writeFinalReport („include ALL the learnings" als `<learning>`-Tags, Quellen = besuchte URLs). Firecrawl; Custom-Endpoint via OPENAI_ENDPOINT.

### Kurz geprüft
- **SakanaAI/AI-Scientist(-v2)** (https://github.com/SakanaAI/AI-Scientist): Ideen → Novelty via Semantic Scholar → Experimente → Write-up abschnittsweise (`ai_scientist/perform_writeup.py`) mit Refinement-Fehlerliste („Numerical results that do not come from explicit experiments and logs"), Zitatrunden `num_cite_rounds`. Cloud-Modelle; „AI Scientist Source Code License" (RAIL-Derivat) mit Offenlegungspflicht.
- **GAIR-NLP/DeepResearcher** (https://github.com/GAIR-NLP/DeepResearcher, arXiv 2504.03160): Qwen2.5-7B, GRPO mit F1-Reward; Browsing-Agent liest „segment by segment" in ein Kurzzeitgedächtnis; Kurzantworten in `<answer>`, keine Berichte. Apache-2.0.
- **HKUDS/Auto-Deep-Research** (https://github.com/HKUDS/Auto-Deep-Research; AutoAgent MIT): `autoagent/fn_call_converter.py` lehrt Tool-Aufrufe als Text `<function=name><parameter=k>v</parameter></function>`, Regex-Rückparsing + Schema-Validierung; Issue #31 zeigt Brüche mit lokalen GGUF-Modellen.
- **LearningCircuit/local-deep-research** (https://github.com/LearningCircuit/local-deep-research, MIT): llama.cpp/Ollama nativ; „~95% on SimpleQA (e.g. Qwen3.6-27B on a 3090)" — allerdings mit der `langgraph-agent`-Strategie (Tool-Calling); daneben source-based, focused-iteration mit `iterations`/`questions_per_iteration`; Report-Modus „Automatic table of contents".
- **langchain-ai/local-deep-researcher** (https://github.com/langchain-ai/local-deep-researcher, MIT): Query → Suche → laufende Zusammenfassung → „reflect on the summary, identifying knowledge gaps" → neue Query, N Schleifen.
- **federicodeponte/opendraft** (https://github.com/federicodeponte/opendraft, MIT): Zitat bleibt nur, wenn „DOI is held by at least two of CrossRef, OpenAlex and Semantic Scholar"; Cloud-LLMs.

## 2. Übertragbar auf unser Produkt

Schwächen: (1) feste, pharma-lastige Suchmuster; (2) Funde erreichen den Schreibschritt nicht als fertige Zeilen; (3) Satzstreichung hinterlässt Bruchstücke.

**M1 — Perspektiven aus Nachbarthemen statt fester Muster (→ 1).** STORM leitet Personas aus den Inhaltsverzeichnissen verwandter Wikipedia-Seiten ab. Unsere Quelle: Titel/CPC-Klassen/Mega-Themes der k nächsten Nachbarn im eigenen Korpus (pgvector) → GenPersona-Prompt → je Persona Fragen → Queries; themenagnostisch, weil die Perspektiven aus den Daten kommen. Ergänzend feste Rollen (Jinas 7 Personas, DeerFlows 8 Achsen) auf unsere Pflichtkapitel gemappt: Historical/Current/Future → „Was sich bewegt", Risk+Stakeholder → „Recht/IP", Temporal → „Kalender", Comparative → „Optionen". 27B: ja — reine Text-Prompts, Bullet-Listen parsen, kein Tool-Calling.

**M2 — Simulierte Frage→Query→Antwort-Konversation (→ 1).** STORMs Writer/Expert-Dialog erzeugt Follow-up-Fragen aus dem schon Gefundenen („every sentence supported by the gathered information"). Für uns: pro Persona 3–4 Turns innerhalb des Brave-Budgets, Antworten nur aus Snippets. 27B: ja; Ende deterministisch über max_turn, nicht über den „Thank you"-Satz.

**M3 — Outline-getriebene Abschnittsrecherche mit Pass/Fail (→ 1, 2).** ODR-Legacy und Jina-DeepResearch fahren je Abschnitt eigene Queries und bewerten. Unsere Gliederung ist fix, also: pro Pflichtkapitel Query-Set aus Kapitelbeschreibung + Thema, Grader = deterministische Belegzählung statt LLM-Grade, follow_up_queries bis max_search_depth. 27B: ja, JSON per llama.cpp-Grammar.

**M4 — Evidence-Memory-Bank mit ID-Zitaten in der Gliederung, abschnittsweises Schreiben mit Pruning (→ 2).** WebWeaver hängt Evidenz-IDs an Outline-Abschnitte; der Writer bekommt je Abschnitt nur diese Zeilen und verwirft sie danach. STORM/Co-STORM tun dasselbe über Cosine-Retrieval bzw. Knoten-Zitatmengen (1500/4000 Wörter Kappe). Das ersetzt unseren 80k-Prompt durch ≤4k Wörter Evidenz je Kapitel. 27B: ja — Retrieval per qwen3-embedding, Numpy-Cosine reicht wie bei STORM, kein Vektorstore.

**M5 — Learnings als atomare Zeilen mit Entität/Zahl/Datum/URL (→ 2).** dzhng („include any entities … exact metrics, numbers, or dates"), GPT-Researcher („Learning [source_url]: <insight>"), ODR compress („rewritten verbatim … ALL sources"), PaperQA2 (Summary + relevance_score, top-N). Für uns: jeder Fund wird direkt nach dem Abruf zu 1–3 Zeilen `{akteur, aussage, zahl/datum, url}` verdichtet und sofort deterministisch gegen die Seite geprüft; nur geprüfte Zeilen wandern in die Bank (M4). 27B: ja; Prompts ≤3k Tokens, JSON-Grammar.

**M6 — Bericht als Gedächtnis statt wachsender Kontext (→ 2).** IterResearch/ReSum: Zustand = Frage + laufender Bericht + letzte Beobachtung. Als Prompt-Muster übertragbar (ReSum „training-free" +4.5 %); Kosten: der Bericht wird jede Runde neu geschrieben — mit 27B nur für die Rechercheschleife sinnvoll.

**M7 — Kritik→Revision statt Streichung (→ 3).** STORM PolishPage („won't delete any non-repeated part … keep the inline citations"), AI-Scientist-Refinement mit Fehlerliste, Jinas getrennter Evaluator, DeerFlow („state 'Information not provided'"). Für uns: der Grounding-Checker liefert die Fehlerliste (ungestützte Zahl X in Satz Y), das Modell schreibt den Absatz neu unter der Regel „ersetze oder streiche nur markierte Aussagen, ändere nichts Unmarkiertes, behalte Zitate", dann erneute deterministische Prüfung, max 2 Runden; Rest → „Nicht-Gestütztes". 27B: ja; eine Zusatzgeneration je betroffenem Kapitel.

**M8 — Explizite Stoppregeln je Recherchezweig (→ 1).** ODR: „3+ relevant sources", „last 2 searches returned similar information", 2–5 Suchen; dzhng: breadth halbiert je Ebene. Als deterministische Budgetregeln in M2/M3 einbaubar, ohne Tool-Calling.

## 3. Was nicht passt
- **Tool-Calling-Loops**: ODR („support structured outputs and tool calling"), DeerFlow v1/v2, local-deep-research `langgraph-agent`, AutoAgents Text-Tool-Format (bricht laut Issue #31 mit lokalen GGUFs). Übernehmbar sind die Prompt-Regeln, nicht die Graphen.
- **RL-trainierte Modelle statt Harness**: Tongyi (30B-A3B, eigene Gewichte), GAIR (7B, Kurzantworten mit F1-Reward), WebWeaver-3k-SFT. Ohne Training bleibt nur die Prompt-Struktur (M4/M6).
- **Vektorstore-/Index-Pflicht**: PaperQA2 baut einen eigenen Chunk-Index und warnt vor kleinen Modellen; STORM-VectorRM braucht Qdrant. Unser pgvector-Korpus ersetzt das; nur die RCS-Idee (Summary + Score je Chunk) übernehmen.
- **Cloud-/Dienst-Bindung**: AI-Scientist (OpenAI/Claude/Gemini, restriktive Lizenz), OpenDraft (Cloud-LLMs; DOI-Prüfung mit lokalem OpenAlex nachbaubar), dzhng (Firecrawl), Jina (Jina Reader/Embeddings, „reasoning model likely needed").
- **Zielform**: STORM/Co-STORM erzeugen Enzyklopädie-Artikel mit generierter Outline; unsere Gliederung (Optionen mit fünf Pflichtfeldern, Kalender) ist fix — nur Kuratierung und Retrieval übertragen.
- **Breite Scraper**: GPT-Researcher scrapt viele URLs je Query — kollidiert mit festen Brave-Budgets und TDM-Compliance.
