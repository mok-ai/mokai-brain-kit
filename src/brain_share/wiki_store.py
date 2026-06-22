import os
from brain_share.wiki_page import WikiPage, render_page

class WikiStore:
    def __init__(self, vault_dir: str, indexer):
        self.vault_dir = vault_dir
        self.indexer = indexer

    def upsert(self, page: WikiPage) -> str:
        if not page.body.strip():
            return ""
        ns_dir = os.path.join(self.vault_dir, page.namespace or "GENERAL")
        os.makedirs(ns_dir, exist_ok=True)
        path = os.path.join(ns_dir, f"{page.topic}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_page(page))
        self.indexer.upsert(
            id=page.topic, text=page.body,
            metadata={"division": page.namespace, "sensitivity": page.sensitivity,
                      "promote": page.promote, "topic": page.topic},
        )
        return path

    def search(self, query: str, top_k: int = 5) -> list:
        out = []
        for r in self.indexer.search(query, top_k):
            r = dict(r); r["collection"] = "wiki"; out.append(r)
        return out
