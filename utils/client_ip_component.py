"""Lấy IP NAT egress của client qua JS fetch api.ipify.org.

Pattern giống utils/scanner_component.py (st.components.v2 + setTriggerValue).
Cache vào session_state để chỉ fetch 1 lần per session.
"""
import streamlit as st


_HTML = '<div id="ipify-loader" style="display:none">Loading IP...</div>'

_JS = """
export default function(component) {
    const { setTriggerValue } = component;
    fetch('https://api.ipify.org?format=json')
        .then(r => r.json())
        .then(data => {
            setTriggerValue('ip', { ip: data.ip, ts: Date.now() });
        })
        .catch(err => {
            setTriggerValue('ip', { ip: null, error: String(err) });
        });
}
"""

_ip_component = st.components.v2.component(
    "client_ip_fetcher",
    html=_HTML,
    js=_JS,
    isolate_styles=False,
)


def get_client_ip(force_refresh: bool = False) -> str | None:
    """Trả về IP NAT egress của client (vd '123.28.109.4').

    Cache vào st.session_state['_client_ip_cached'] để không fetch lại
    mỗi lần dialog rerun. force_refresh=True để bypass cache.
    """
    cache_key = "_client_ip_cached"
    if not force_refresh and st.session_state.get(cache_key):
        return st.session_state[cache_key]

    result = _ip_component(key="client_ip_fetcher_global")
    if result and getattr(result, "ip", None):
        data = result.ip
        ip = data.get("ip") if isinstance(data, dict) else None
        if ip:
            st.session_state[cache_key] = ip
            return ip
    return None
