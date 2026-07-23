"""Extração best-effort de UF a partir do campo `location` de perfis do X."""
from __future__ import annotations

import re
import unicodedata

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

_NAMES = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso do sul": "MS", "mato grosso": "MT",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
    # capitais e cidades grandes
    "rio branco": "AC", "maceio": "AL", "macapa": "AP", "manaus": "AM",
    "salvador": "BA", "fortaleza": "CE", "brasilia": "DF", "vitoria": "ES",
    "goiania": "GO", "sao luis": "MA", "campo grande": "MS", "cuiaba": "MT",
    "belo horizonte": "MG", "belem": "PA", "joao pessoa": "PB", "curitiba": "PR",
    "recife": "PE", "teresina": "PI", "natal": "RN", "porto alegre": "RS",
    "porto velho": "RO", "boa vista": "RR", "florianopolis": "SC",
    "aracaju": "SE", "palmas": "TO", "campinas": "SP", "santos": "SP",
    "niteroi": "RJ",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def extract_uf(location: str | None) -> str | None:
    """Tenta extrair a UF de um texto livre de localização. None se não der."""
    if not location:
        return None
    norm = _normalize(location)
    # nomes de estados/cidades (mais específicos primeiro)
    for name in sorted(_NAMES, key=len, reverse=True):
        if name in norm:
            return _NAMES[name]
    # siglas como palavra isolada ("Santos, SP", "SP - Brasil")
    for token in re.findall(r"\b([a-z]{2})\b", norm):
        if token.upper() in UFS:
            return token.upper()
    return None
