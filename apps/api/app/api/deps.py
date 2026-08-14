from fastapi import Header


def scope_organisation(x_organisation_id: str | None = Header(default=None, alias="X-Organisation-ID")) -> str | None:
    return x_organisation_id
