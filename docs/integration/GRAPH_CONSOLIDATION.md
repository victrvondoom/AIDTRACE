# Graph consolidation

- **FalkorDB** (`FALKORDB_URL`, one instance) now backs: the Evidence Drift site graphs (`<prefix>__<site>`), ResolveAI consumer cases (`resolve_consumer_<site>`), fraud networks and agent runs (`fraud_<site>`), GreenChain scenario graphs (`greenchain_<site>`). The site always comes from the token, never the request. Labels and relationships written by the GreenChain adapter are allow-listed.
- **Neo4j** still owns the existing industrial asset/document graph; nothing was migrated or removed. The RESOLVE-AI-main worker brings its own Neo4j/Qdrant needs and is isolated behind the gateway.
- **Graph Lab** reads any of these graphs in one shape (`nodes`, `edges`, edge direction dependent to dependency) and runs the same ten engines on them. Verified: its blast radius equals `FalkorDriftStore.find_impacts` on real FalkorDB.
- **Not done:** a single ontology across domains (each keeps its own labels), cross-domain evidence linking, and a Neo4j to FalkorDB migration.