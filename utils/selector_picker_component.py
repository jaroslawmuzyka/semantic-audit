"""Cienki wrapper deklarujący komponent Streamlit dla interaktywnego podglądu
(utils/assets/selector_picker_component/index.html). Cała logika przetwarzania
HTML-a mieszka w utils/selector_picker.py — ten plik tylko go renderuje.

Odseparowane od selector_picker.py celowo: ten moduł zależy od Streamlit i musi
być wywoływany w trakcie renderowania strony, podczas gdy selector_picker.py
jest czystym Pythonem (łatwym do testowania bez uruchamiania całej aplikacji).
"""
import os
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "assets", "selector_picker_component")
_component = components.declare_component("audit_selector_picker", path=_COMPONENT_DIR)


def render_picker(html_fragment: str, key: str):
    """Renderuje podgląd. Zwraca None (nic jeszcze nie kliknięto) albo
    {"selector": str, "action": "exclude"|"target", "nonce": str} po kliknięciu
    „Wyklucz”/„Celuj” w komponencie."""
    return _component(html=html_fragment, key=key, default=None)
