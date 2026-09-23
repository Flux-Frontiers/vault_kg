"""viz3d.py -- interactive 3-D viewer for a vault grown as a tree.

A ``QMainWindow`` around a ``pyvistaqt.QtInteractor`` showing what
:func:`vaultkg.scene.build_vault_tree_scene` composes. ``QtInteractor`` gives
orbit, zoom and pan through VTK's default interactor style. One toolbar
action, Cast to Looking Glass, is wired to
``kg_utils.viz3d.qt.cast_scene_to_looking_glass``, as in genealogy_kg.

This module imports PyQt5 and pyvistaqt at module scope, so only the
``vaultkg viz3d`` command imports it, and only after checking both exist.
"""

from __future__ import annotations

from pathlib import Path

from kg_utils.viz3d import frame_tree
from kg_utils.viz3d.qt import DEFAULT_QUILT_PRESET, cast_scene_to_looking_glass
from PyQt5.QtWidgets import QAction, QMainWindow, QMessageBox, QToolBar
from pyvistaqt import QtInteractor

from vaultkg import scene as render3d
from vaultkg.module import VaultKG


class VaultTreeWindow(QMainWindow):
    """Main window: one grown vault, orbit/zoom/pan, one Cast action.

    :param kg: An open vault graph.
    :param group_by: ``"auto"``, ``"folder"`` or ``"tag"``.
    :param color_by: ``"group"``, ``"tag"`` or ``"links"``.
    :param size_by: ``"links"`` or ``"none"``.
    :param preset: Quilt preset name for the Cast action.
    :param organic: ``True`` grows wood; ``False`` draws the schematic.
    """

    def __init__(
        self,
        kg: VaultKG,
        *,
        group_by: str = "auto",
        color_by: str = "group",
        size_by: str = "links",
        preset: str = DEFAULT_QUILT_PRESET,
        organic: bool = True,
    ) -> None:
        super().__init__()
        self._kg = kg
        self._preset = preset

        def build(plotter) -> render3d.VaultTree:
            return render3d.build_vault_tree_scene(
                kg,
                plotter,
                group_by=group_by,
                color_by=color_by,
                size_by=size_by,
                organic=organic,
            )

        self._build = build
        self.plotter = QtInteractor(self)
        self.setCentralWidget(self.plotter)
        tree = build(self.plotter)
        self.setWindowTitle(f"VaultKG viz3d -- {tree.title}")

        frame = frame_tree(tree.points)
        self.plotter.camera.position = frame.position
        self.plotter.camera.focal_point = frame.focal_point
        self.plotter.camera.up = frame.up
        self.plotter.reset_camera()

        toolbar = QToolBar("Actions", self)
        self.addToolBar(toolbar)
        cast_action = QAction("Cast to Looking Glass", self)
        cast_action.triggered.connect(self._cast)
        toolbar.addAction(cast_action)

    def _cast(self) -> None:
        """Render the current view off-screen and send it to Looking Glass Bridge."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 -- viz3d-only import

        result = cast_scene_to_looking_glass(
            self._build,
            self.plotter.camera_position,
            Path("renders") / f"{self._kg.repo_root.name}_cast",
            QUILT_PRESETS[self._preset],
        )
        box = QMessageBox.information if result.path else QMessageBox.warning
        box(self, "Cast to Looking Glass", result.message)


def launch(
    vault: Path,
    *,
    group_by: str = "auto",
    color_by: str = "group",
    size_by: str = "links",
    preset: str = DEFAULT_QUILT_PRESET,
    organic: bool = True,
    width: int = 1400,
    height: int = 900,
) -> None:
    """Open the interactive viewer on a built vault.

    :param vault: Vault root; the graph lives in ``<vault>/.vaultkg/``.
    :param group_by: ``"auto"``, ``"folder"`` or ``"tag"``.
    :param color_by: ``"group"``, ``"tag"`` or ``"links"``.
    :param size_by: ``"links"`` or ``"none"``.
    :param preset: Quilt preset name for the Cast action.
    :param organic: ``True`` grows wood; ``False`` draws the schematic.
    :param width: Window width in pixels.
    :param height: Window height in pixels.
    :raises ValueError: If the vault has no notes, or an option is unknown.
    """
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415 -- viz3d-only import

    with VaultKG(vault) as kg:
        app = QApplication.instance() or QApplication([])
        window = VaultTreeWindow(
            kg,
            group_by=group_by,
            color_by=color_by,
            size_by=size_by,
            preset=preset,
            organic=organic,
        )
        window.resize(width, height)
        window.show()
        app.exec_()


__all__ = ["VaultTreeWindow", "launch"]
