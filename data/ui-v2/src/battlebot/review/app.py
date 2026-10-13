"""FastAPI app for local profile review."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Form, Query, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from battlebot.review import service


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="Battlebot Profile Review")
    app.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_DIR / "static")),
        name="static",
    )

    @app.get("/")
    async def index(
        request: Request,
        kind: str = Query("needs_review"),
        franchise: str | None = None,
        category: str | None = None,
        warning_flag: str | None = None,
    ):
        profiles = service.list_profiles(
            kind=kind,
            franchise=franchise,
            category=category,
            warning_flag=warning_flag,
            limit=500,
        )
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "profiles": profiles,
                "kind": kind,
                "franchise": franchise or "",
                "category": category or "",
                "warning_flag": warning_flag or "",
            },
        )

    @app.get("/profile")
    async def profile_detail(request: Request, path: str):
        if not Path(path).exists():
            raise HTTPException(status_code=404, detail="Profile not found")
        return templates.TemplateResponse(
            request,
            "profile.html",
            {"request": request, "profile": service.inspect_profile(path)},
        )

    @app.post("/note")
    async def add_note(
        path: Annotated[str, Form()],
        field_path: Annotated[str, Form()] = "",
        issue_type: Annotated[str, Form()] = "review_note",
        note: Annotated[str, Form()] = "",
        suggested_value: Annotated[str, Form()] = "",
    ):
        service.add_review_note(
            path,
            field_path=field_path,
            issue_type=issue_type,
            note=note,
            suggested_value=suggested_value,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/add-source")
    async def add_source(
        path: Annotated[str, Form()],
        source_id: Annotated[str, Form()] = "",
        title: Annotated[str, Form()] = "",
        url: Annotated[str, Form()] = "",
        source_type: Annotated[str, Form()] = "manual",
        revision_id: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
    ):
        service.add_source(
            path,
            source_id=source_id,
            title=title,
            url=url,
            source_type=source_type,
            revision_id=revision_id,
            notes=notes,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/set-core")
    async def set_core(
        path: Annotated[str, Form()],
        field: Annotated[str, Form()],
        text: Annotated[str, Form()],
        source_id: Annotated[str, Form()],
        confidence: Annotated[float, Form()],
        note: Annotated[str, Form()] = "",
    ):
        service.set_core_field(
            path,
            field=field,
            text=text,
            source_id=source_id,
            confidence=confidence,
            note=note,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/add-ability")
    async def add_ability(
        path: Annotated[str, Form()],
        item_id: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        source_id: Annotated[str, Form()] = "",
        confidence: Annotated[float, Form()] = 0.75,
        tags: Annotated[str, Form()] = "",
    ):
        service.add_ability(
            path,
            item_id=item_id,
            name=name,
            description=description,
            source_id=source_id,
            confidence=confidence,
            tags=tags,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/add-weakness")
    async def add_weakness(
        path: Annotated[str, Form()],
        item_id: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        source_id: Annotated[str, Form()] = "",
        confidence: Annotated[float, Form()] = 0.75,
        tags: Annotated[str, Form()] = "",
    ):
        service.add_weakness(
            path,
            item_id=item_id,
            name=name,
            description=description,
            source_id=source_id,
            confidence=confidence,
            tags=tags,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/approve")
    async def approve(path: Annotated[str, Form()], force: Annotated[bool, Form()] = False):
        service.approve_profile(path, force=force)
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/reject")
    async def reject(path: Annotated[str, Form()], note: Annotated[str, Form()] = ""):
        service.reject_profile(path, note=note)
        return RedirectResponse("/", status_code=303)

    @app.post("/requeue")
    async def requeue(path: Annotated[str, Form()], note: Annotated[str, Form()] = ""):
        service.requeue_profile(path, note=note)
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    @app.post("/auto-repair-selected")
    async def auto_repair_selected(
        path: Annotated[str, Form()],
        source_id: Annotated[str, Form()],
        promote_if_valid: Annotated[bool, Form()] = False,
    ):
        await service.selected_auto_repair(
            path,
            source_id,
            promote_if_valid=promote_if_valid,
        )
        return RedirectResponse(f"/profile?path={path}", status_code=303)

    return app


app = create_app()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local profile review UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--reload", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    uvicorn.run(
        "battlebot.review.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
