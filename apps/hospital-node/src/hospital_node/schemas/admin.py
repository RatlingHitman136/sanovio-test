from pydantic import BaseModel


class SigningKeyView(BaseModel):
    kid: str
    public_jwk: dict[str, str]
    fingerprint: str


class ResetSeed(BaseModel):
    dataset: str = "demo_ksp"


class SeedResult(BaseModel):
    dataset: str
    users: int
    articles: int
