from znactime.ui.qt import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from znactime.ui.qt.theme import DARK_THEME, LIGHT_THEME, SYSTEM_THEME


class AppearanceDialog(QDialog):
    def __init__(self, parent, theme_controller):
        super().__init__(parent)
        self.theme_controller = theme_controller
        self.setWindowTitle("Settings")
        self.resize(520, 300)

        self.navigation = QListWidget(self)
        self.navigation.setFixedWidth(160)
        QListWidgetItem("Color scheme", self.navigation)
        self.navigation.setCurrentRow(0)

        self.pages = QStackedWidget(self)
        self.pages.addWidget(self._build_appearance_page())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, stretch=1)

    def _build_appearance_page(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 0, 0)

        frame = QFrame(page)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(18, 16, 18, 16)
        frame_layout.addWidget(QLabel("Color scheme", frame))

        self.system_radio = QRadioButton("System theme", frame)
        self.light_radio = QRadioButton("Light", frame)
        self.dark_radio = QRadioButton("Dark", frame)

        self.button_group = QButtonGroup(frame)
        self.button_group.addButton(self.system_radio, 0)
        self.button_group.addButton(self.light_radio, 1)
        self.button_group.addButton(self.dark_radio, 2)

        frame_layout.addWidget(self.system_radio)
        frame_layout.addWidget(self.light_radio)
        frame_layout.addWidget(self.dark_radio)
        frame_layout.addStretch(1)

        self._sync_checked_button()
        self.button_group.idClicked.connect(self._set_theme)

        layout.addWidget(frame)
        layout.addStretch(1)
        return page

    def _sync_checked_button(self):
        if self.theme_controller.mode == LIGHT_THEME:
            self.light_radio.setChecked(True)
        elif self.theme_controller.mode == DARK_THEME:
            self.dark_radio.setChecked(True)
        else:
            self.system_radio.setChecked(True)

    def _set_theme(self, button_id):
        if button_id == 1:
            self.theme_controller.set_mode(LIGHT_THEME)
        elif button_id == 2:
            self.theme_controller.set_mode(DARK_THEME)
        else:
            self.theme_controller.set_mode(SYSTEM_THEME)
