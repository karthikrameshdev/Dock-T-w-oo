"""Vault T(w)oo application attached drawer."""

from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class VaultCard(QFrame):
    """Modern credential card with masking and copy actions."""

    def __init__(self, title: str, username: str, secret: str, custom_field: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.title_str = title
        self.username_str = username
        self.secret_str = secret
        self.custom_str = custom_field
        self._revealed = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("VaultCard")
        self.setStyleSheet(
            """
            QFrame#VaultCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 12px;
            }
            QFrame#VaultCard:hover {
                border-color: rgba(255, 255, 255, 0.16);
                background: rgba(255, 255, 255, 0.06);
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title row
        title_row = QHBoxLayout()
        title_lbl = QLabel(self.title_str, self)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #ffffff;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        copy_all_btn = QPushButton("Copy", self)
        copy_all_btn.setFixedSize(50, 22)
        copy_all_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(59, 130, 246, 0.2);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 6px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #3b82f6;
                color: #ffffff;
            }
            """
        )
        copy_all_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.secret_str))
        title_row.addWidget(copy_all_btn)
        layout.addLayout(title_row)

        # Username row
        if self.username_str:
            user_row = QHBoxLayout()
            user_lbl = QLabel(f"User: {self.username_str}", self)
            user_lbl.setStyleSheet("font-size: 11px; color: #8e8e9f;")
            user_row.addWidget(user_lbl)
            user_row.addStretch()

            user_copy = QPushButton("Copy User", self)
            user_copy.setFixedSize(65, 20)
            user_copy.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    color: #a1a1aa;
                    border: none;
                    font-size: 10px;
                }
                QPushButton:hover {
                    color: #ffffff;
                }
                """
            )
            user_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.username_str))
            user_row.addWidget(user_copy)
            layout.addLayout(user_row)

        # Password / Secret row
        secret_row = QHBoxLayout()
        self.secret_display = QLabel("••••••••••••••••", self)
        self.secret_display.setStyleSheet("font-size: 11px; font-family: monospace; color: #cbd5e1;")
        secret_row.addWidget(self.secret_display)
        secret_row.addStretch()

        self.toggle_eye = QPushButton("👁 Show", self)
        self.toggle_eye.setFixedSize(60, 20)
        self.toggle_eye.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border-radius: 4px;
                border: none;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            """
        )
        self.toggle_eye.clicked.connect(self._toggle_reveal)
        secret_row.addWidget(self.toggle_eye)
        layout.addLayout(secret_row)

        # Custom field
        if self.custom_str:
            custom_lbl = QLabel(self.custom_str, self)
            custom_lbl.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
            layout.addWidget(custom_lbl)

    def _toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        if self._revealed:
            self.secret_display.setText(self.secret_str)
            self.toggle_eye.setText("🔒 Hide")
        else:
            self.secret_display.setText("••••••••••••••••")
            self.toggle_eye.setText("👁 Show")


class VaultAppWidget(BaseAttachedApp):
    """Vault T(w)oo drawer showing encrypted cards, live search, and credential management."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("vault", "Vault T(w)oo", config, parent)
        self._cards: List[VaultCard] = []
        self._init_vault_ui()

    def _init_vault_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Search Bar
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search passwords, tokens, API keys...")
        self.search_bar.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
            """
        )
        self.search_bar.textChanged.connect(self._filter_cards)
        self.content_layout.addWidget(self.search_bar)

        # Scroll Area for Cards
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget(self.scroll)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(10)

        self._populate_sample_vault_items()

        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_container)
        self.content_layout.addWidget(self.scroll, 1)

    def _populate_sample_vault_items(self) -> None:
        sample_items = [
            ("GitHub Personal Access Token", "karthikrameshdev", "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", "Scope: repo, workflow, gist"),
            ("Production Stripe API Key", "billing_admin", "sk_live_9488f780f29103c834a8e", "Webhook: whsec_live_99218204"),
            ("AWS Root IAM Credentials", "admin@cloud.infra", "AKIA479102BF84EXAMPLE", "Region: us-east-1"),
            ("OpenRouter Platform Key", "karthik.ramesh", "sk-or-v1-37b55f794d6969fd22631badf94095ac", "Model: anthropic/claude-3.5-sonnet"),
            ("Database Cluster Connection", "postgres_master", "pg_prod_cluster_#a783!k", "Port: 5432, Host: db.internal"),
        ]

        for title, user, secret, custom in sample_items:
            card = VaultCard(title, user, secret, custom, self.cards_container)
            self._cards.append(card)
            self.cards_layout.addWidget(card)

    def _filter_cards(self, query: str) -> None:
        query = query.lower()
        for card in self._cards:
            matches = (
                query in card.title_str.lower()
                or query in card.username_str.lower()
                or query in card.custom_str.lower()
            )
            card.setHidden(not matches)
