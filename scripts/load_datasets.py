#!/usr/bin/env python3
"""
GraphRAG Platform — Dataset Loader
Loads sample legal documents for demo/testing.
"""

import json
import sys
import time

import requests

API_BASE = "http://localhost:8000/api/v1"

# Sample Russian legal documents for demo
SAMPLE_DOCUMENTS = [
    {
        "title": "Гражданский кодекс РФ — Статья 1",
        "text": (
            "Гражданское законодательство основывается на признании равенства участников "
            "регулируемых им отношений, неприкосновенности собственности, свободы договора, "
            "недопустимости произвольного вмешательства кого-либо в частные дела, "
            "необходимости беспрепятственного осуществления гражданских прав, обеспечения "
            "восстановления нарушенных прав, их судебной защиты."
        ),
        "clearance_level": "unclassified",
        "department": "legal",
    },
    {
        "title": "Трудовой кодекс РФ — Статья 2",
        "text": (
            "Исходя из общепризнанных принципов и норм международного права и в соответствии "
            "с Конституцией Российской Федерации основными принципами правового регулирования "
            "трудовых отношений и иных непосредственно связанных с ними отношений признаются: "
            "свобода труда, включая право на труд, который каждый свободно выбирает или на "
            "который свободно соглашается, право распоряжаться своими способностями к труду, "
            "выбирать профессию и род деятельности."
        ),
        "clearance_level": "unclassified",
        "department": "legal",
    },
    {
        "title": "Федеральный закон о персональных данных",
        "text": (
            "Настоящим Федеральным законом регулируются отношения, связанные с обработкой "
            "персональных данных, осуществляемой федеральными органами государственной власти, "
            "органами государственной власти субъектов Российской Федерации, иными "
            "государственными органами, органами местного самоуправления, юридическими лицами, "
            "физическими лицами с использованием средств автоматизации."
        ),
        "clearance_level": "confidential",
        "department": "legal",
    },
    {
        "title": "Внутренний регламент — Политика безопасности",
        "text": (
            "Доступ к конфиденциальным документам предоставляется только сотрудникам "
            "с соответствующим уровнем допуска. Все операции с секретными материалами "
            "должны быть зарегистрированы в журнале аудита. Передача документов за пределы "
            "организации требует письменного разрешения руководителя отдела безопасности."
        ),
        "clearance_level": "secret",
        "department": "management",
    },
]


def get_auth_token(email: str = "admin@graphrag.local", password: str = "Admin123!") -> str:
    """Authenticate and get JWT token."""
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"  ✗ Auth failed: {resp.status_code} — {resp.text}")
        sys.exit(1)
    return resp.json()["access_token"]


def load_documents(token: str):
    """Ingest sample documents via API."""
    headers = {"Authorization": f"Bearer {token}"}

    for doc in SAMPLE_DOCUMENTS:
        try:
            resp = requests.post(
                f"{API_BASE}/ingest/text",
                json={
                    "text": doc["text"],
                    "title": doc["title"],
                    "clearance_level": doc["clearance_level"],
                    "department": doc["department"],
                },
                headers=headers,
                timeout=120,
            )
            if resp.status_code in (200, 201):
                print(f"  ✓ Loaded: {doc['title']}")
            else:
                print(f"  ✗ Failed: {doc['title']} — {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  ✗ Error:  {doc['title']} — {e}")


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║  GraphRAG — Loading Sample Datasets          ║")
    print("╚══════════════════════════════════════════════╝")

    print("\n▸ Authenticating as admin...")
    token = get_auth_token()
    print("  ✓ Authenticated")

    print("\n▸ Loading documents...")
    load_documents(token)

    print("\n  ✓ Dataset loading complete!")


if __name__ == "__main__":
    main()
