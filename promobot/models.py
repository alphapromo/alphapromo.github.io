from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Deal:
    loja: str                 # "Mercado Livre" | "Amazon"
    id: str                   # MLB123 / ASIN
    titulo: str
    preco: float
    preco_original: float
    imagem: str
    url: str                  # link do produto (sem afiliado)
    categoria: str = ""
    frete_gratis: bool = False
    popularidade: float = 0.0  # vendidos, avaliações etc.
    link_afiliado: str = ""
    score: float = 0.0
    extras: dict = field(default_factory=dict)

    @property
    def desconto(self) -> int:
        if self.preco_original and self.preco_original > self.preco:
            return round((1 - self.preco / self.preco_original) * 100)
        return 0

    @property
    def chave(self) -> str:
        return f"{self.loja}:{self.id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["desconto"] = self.desconto
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Deal":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)


def brl(valor: float) -> str:
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"
