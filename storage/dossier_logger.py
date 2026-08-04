"""
dossier logger — structured JSON dossier file management
exports dossiers, manages output directories, file cleanup
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DossierLogger:
    """
    manages dossier JSON file export and retrieval

    usage:
        logger = DossierLogger(output_dir="output")
        filepath = await logger.save_dossier(username="john_doe_", dossier_dict={...})
        all_dossiers = await logger.list_dossiers()
    """

    def __init__(
        self,
        output_dir: str = "output",
        pretty_print: bool = True,
        max_dossiers_per_target: int = 10,
    ):
        self.output_dir = Path(output_dir)
        self.dossiers_dir = self.output_dir / "dossiers"
        self.images_dir = self.output_dir / "images"
        self.pretty_print = pretty_print
        self.max_dossiers_per_target = max_dossiers_per_target

        # ensure directories exist
        self.dossiers_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    async def save_dossier(self, username: str, dossier_data: dict,
                           dossier_id: str = "") -> str:
        """
        save dossier as JSON file
        returns the filepath
        """
        safe_username = username.replace("/", "_").replace("\\", "_")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

        if not dossier_id:
            dossier_id = f"dossier_{safe_username}_{timestamp}"

        filename = f"{safe_username}_{timestamp}.json"
        filepath = self.dossiers_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                dossier_data,
                f,
                indent=2 if self.pretty_print else None,
                ensure_ascii=False,
                default=str,
            )

        file_size = filepath.stat().st_size
        logger.info("[logger] dossier saved: %s (%s)", filename, self._format_size(file_size))

        # cleanup old dossiers for this target
        await self._cleanup_old_dossiers(safe_username)

        return str(filepath)

    async def save_image(self, username: str, image_data: bytes,
                         image_type: str = "profile_pic") -> str:
        """save a downloaded image, returns filepath"""
        safe_username = username.replace("/", "_").replace("\\", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_username}_{image_type}_{timestamp}.jpg"
        filepath = self.images_dir / filename

        with open(filepath, "wb") as f:
            f.write(image_data)

        logger.debug("[logger] image saved: %s (%s)", filename, self._format_size(len(image_data)))
        return str(filepath)

    async def load_dossier(self, filepath: str) -> Optional[dict]:
        """load a dossier from file"""
        path = Path(filepath)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def list_dossiers(self, username: str = None) -> list[dict]:
        """list dossiers, optionally filtered by username"""
        if not self.dossiers_dir.exists():
            return []

        files = sorted(
            self.dossiers_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        dossiers = []
        for fp in files:
            if username:
                safe = username.replace("/", "_").replace("\\", "_")
                if safe not in fp.stem:
                    continue

            stat = fp.stat()
            dossiers.append({
                "filename": fp.name,
                "filepath": str(fp),
                "size_bytes": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return dossiers

    async def list_images(self, username: str = None) -> list[dict]:
        """list downloaded images"""
        if not self.images_dir.exists():
            return []

        files = sorted(
            self.images_dir.glob("*.jpg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        images = []
        for fp in files:
            if username:
                safe = username.replace("/", "_").replace("\\", "_")
                if safe not in fp.stem:
                    continue

            stat = fp.stat()
            images.append({
                "filename": fp.name,
                "filepath": str(fp),
                "size_bytes": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return images

    async def delete_dossier(self, filepath: str) -> bool:
        """delete a specific dossier file"""
        path = Path(filepath)
        if path.exists() and path.parent == self.dossiers_dir:
            path.unlink()
            logger.info("[logger] deleted: %s", path.name)
            return True
        return False

    async def get_output_size(self) -> dict:
        """get total size of all output files"""
        total_dossier_size = sum(
            f.stat().st_size for f in self.dossiers_dir.glob("*.json")
            if f.is_file()
        )
        total_image_size = sum(
            f.stat().st_size for f in self.images_dir.glob("*.jpg")
            if f.is_file()
        )
        return {
            "dossiers_size_bytes": total_dossier_size,
            "dossiers_size_formatted": self._format_size(total_dossier_size),
            "images_size_bytes": total_image_size,
            "images_size_formatted": self._format_size(total_image_size),
            "total_size_formatted": self._format_size(total_dossier_size + total_image_size),
            "dossier_count": len(list(self.dossiers_dir.glob("*.json"))),
            "image_count": len(list(self.images_dir.glob("*.jpg"))),
        }

    # ─── internal ───────────────────────────────────────────────────

    async def _cleanup_old_dossiers(self, safe_username: str):
        """remove oldest dossiers if exceeding max per target"""
        pattern = f"{safe_username}_*.json"
        files = sorted(
            self.dossiers_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        while len(files) > self.max_dossiers_per_target:
            oldest = files.pop()
            oldest.unlink()
            logger.debug("[logger] cleaned old dossier: %s", oldest.name)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """format bytes to human readable"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"