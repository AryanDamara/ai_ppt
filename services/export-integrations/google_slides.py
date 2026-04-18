"""
Google Slides export service — converts deck JSON to a Google Slides presentation.

REQUIREMENTS:
  - Google Cloud project with Slides API enabled
  - User provides OAuth token with scope: https://www.googleapis.com/auth/presentations
  - Install: pip install google-api-python-client google-auth-httplib2

BATCH API:
  Uses batchUpdate for efficiency — sends all slide creation in one API call.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GoogleSlidesExporter:
    """Converts deck JSON to a Google Slides presentation via the Slides API."""

    def __init__(self, oauth_token: str):
        self._token = oauth_token
        self._service = None

    def _get_service(self):
        """Initialise the Google Slides API service."""
        if self._service is None:
            try:
                from googleapiclient.discovery import build
                from google.oauth2.credentials import Credentials

                creds = Credentials(token=self._token)
                self._service = build("slides", "v1", credentials=creds)
            except ImportError:
                raise RuntimeError(
                    "Google API client not installed. "
                    "Install: pip install google-api-python-client google-auth"
                )
        return self._service

    async def export_deck(self, deck_json: dict, title: str = "AI Presentation") -> dict:
        """
        Export a complete deck to Google Slides.

        Returns dict with:
          slides_url : URL to the created presentation
          google_presentation_id : Google Slides ID
          slide_count : number of slides created
        """
        import asyncio

        # Run in executor since Google API client is synchronous
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._export_sync, deck_json, title)

    def _export_sync(self, deck_json: dict, title: str) -> dict:
        """Synchronous export implementation."""
        service = self._get_service()

        # Step 1: Create empty presentation
        presentation = service.presentations().create(
            body={"title": title}
        ).execute()
        presentation_id = presentation["presentationId"]

        slides = deck_json.get("slides", [])
        if not slides:
            return {
                "slides_url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
                "google_presentation_id": presentation_id,
                "slide_count": 0,
            }

        # Step 2: Build batch update requests
        requests = []

        for i, slide in enumerate(slides):
            slide_type = slide.get("slide_type", "content_bullets")
            content = slide.get("content", {})

            # Create a new slide
            slide_object_id = f"slide_{i}"
            layout = self._map_layout(slide_type)

            requests.append({
                "createSlide": {
                    "objectId": slide_object_id,
                    "insertionIndex": i,
                    "slideLayoutReference": {
                        "predefinedLayout": layout,
                    },
                }
            })

            # Add title text
            title_text = content.get("headline", slide.get("action_title", ""))
            if title_text:
                title_id = f"title_{i}"
                requests.extend(self._create_text_box(
                    slide_id=slide_object_id,
                    element_id=title_id,
                    text=title_text,
                    x_pt=50, y_pt=30,
                    width_pt=620, height_pt=60,
                    font_size=28, bold=True,
                ))

            # Add content based on slide type
            if slide_type == "content_bullets":
                bullets = content.get("bullets", [])
                for j, bullet in enumerate(bullets):
                    bullet_text = bullet.get("text", "")
                    if bullet_text:
                        bullet_id = f"bullet_{i}_{j}"
                        y_offset = 120 + (j * 50)
                        requests.extend(self._create_text_box(
                            slide_id=slide_object_id,
                            element_id=bullet_id,
                            text=f"• {bullet_text}",
                            x_pt=70, y_pt=y_offset,
                            width_pt=580, height_pt=40,
                            font_size=16, bold=False,
                        ))

            elif slide_type == "title_slide":
                subtitle = content.get("subheadline", "")
                if subtitle:
                    sub_id = f"subtitle_{i}"
                    requests.extend(self._create_text_box(
                        slide_id=slide_object_id,
                        element_id=sub_id,
                        text=subtitle,
                        x_pt=50, y_pt=100,
                        width_pt=620, height_pt=40,
                        font_size=18, bold=False,
                    ))

            elif slide_type == "section_divider":
                section_title = content.get("section_title", "")
                if section_title:
                    sec_id = f"section_{i}"
                    requests.extend(self._create_text_box(
                        slide_id=slide_object_id,
                        element_id=sec_id,
                        text=section_title,
                        x_pt=50, y_pt=200,
                        width_pt=620, height_pt=80,
                        font_size=36, bold=True,
                    ))

            elif slide_type == "visual_split":
                text = content.get("supporting_text", "")
                if text:
                    text_id = f"visual_text_{i}"
                    requests.extend(self._create_text_box(
                        slide_id=slide_object_id,
                        element_id=text_id,
                        text=text,
                        x_pt=50, y_pt=120,
                        width_pt=300, height_pt=250,
                        font_size=14, bold=False,
                    ))

        # Delete the default blank slide
        default_slides = presentation.get("slides", [])
        if default_slides:
            requests.insert(0, {
                "deleteObject": {
                    "objectId": default_slides[0]["objectId"],
                }
            })

        # Step 3: Execute batch update with retry
        if requests:
            for attempt in range(3):
                try:
                    service.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": requests},
                    ).execute()
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"Google Slides batch update failed: {e}")
                        raise
                    logger.warning(f"Retry {attempt+1} for batch update: {e}")
                    import time
                    time.sleep(2 ** attempt)

        slides_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
        logger.info(f"Google Slides export complete: {slides_url}")

        return {
            "slides_url": slides_url,
            "google_presentation_id": presentation_id,
            "slide_count": len(slides),
        }

    @staticmethod
    def _map_layout(slide_type: str) -> str:
        """Map internal slide types to Google Slides predefined layouts."""
        mapping = {
            "title_slide":      "TITLE",
            "content_bullets":  "TITLE_AND_BODY",
            "data_chart":       "TITLE_AND_BODY",
            "visual_split":     "TITLE_AND_TWO_COLUMNS",
            "table":            "TITLE_AND_BODY",
            "section_divider":  "SECTION_HEADER",
        }
        return mapping.get(slide_type, "BLANK")

    @staticmethod
    def _create_text_box(
        slide_id: str,
        element_id: str,
        text: str,
        x_pt: float,
        y_pt: float,
        width_pt: float,
        height_pt: float,
        font_size: int = 16,
        bold: bool = False,
    ) -> list[dict]:
        """Create a text box element on a slide."""
        EMU = 12700  # 1 pt = 12700 EMU

        return [
            {
                "createShape": {
                    "objectId": element_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width":  {"magnitude": width_pt * EMU, "unit": "EMU"},
                            "height": {"magnitude": height_pt * EMU, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": x_pt * EMU,
                            "translateY": y_pt * EMU,
                            "unit": "EMU",
                        },
                    },
                }
            },
            {
                "insertText": {
                    "objectId": element_id,
                    "text": text,
                    "insertionIndex": 0,
                }
            },
            {
                "updateTextStyle": {
                    "objectId": element_id,
                    "style": {
                        "fontSize": {"magnitude": font_size, "unit": "PT"},
                        "bold": bold,
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "fontSize,bold",
                }
            },
        ]
