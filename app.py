"""
app.py — Interfaz web de la aplicación (Streamlit).

Ejecutar con:  streamlit run app.py
"""
import html

import pandas as pd
import streamlit as st

from logica import (
    ACIERTOS_PARA_SUBIR,
    NIVEL_MAXIMO,
    NIVELES,
    ErrorSintaxis,
    a_texto,
    analizar,
    canonico,
    clasificar,
    contraejemplo,
    equivalentes,
    evaluar,
    formula_ley,
    generar_pregunta,
    generar_tabla,
    identificar_leyes,
    ordenar_variables,
    variables_de,
)

st.set_page_config(page_title="Lógica Proposicional", page_icon="🧠", layout="wide")

st.markdown(
    """
    <style>
    .formula {
        font-family: 'Courier New', monospace; font-size: 1.2rem;
        padding: .8rem 1rem; margin: .5rem 0 1rem 0;
        background: rgba(127,127,127,.08);
        border-left: 4px solid #6366f1; border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PAGINAS = {
    "Inicio": "inicio",
    "Tabla de verdad": "tabla",
    "A · Equivalencias": "equivalencias",
    "B · Trivia de leyes": "trivia",
}


# ---------------------------------------------------------------------------
# Utilidades de interfaz
# ---------------------------------------------------------------------------
def mostrar_formula(texto: str) -> None:
    st.markdown(f"<div class='formula'>{html.escape(texto)}</div>",
                unsafe_allow_html=True)


def mostrar_error_sintaxis(error: Exception) -> None:
    st.error(f"Error de sintaxis: {error}")
    st.caption("Corrige la expresión y vuelve a intentarlo. Revisa paréntesis, "
               "operadores bien ubicados y que las variables sean solo p, q o r.")


def estilo_tabla(df: pd.DataFrame):
    """Colorea V en verde y F en rojo (compatible con pandas antiguo y nuevo)."""
    def colorear(valor):
        if valor == "V":
            return "color:#15803d;font-weight:700"
        if valor == "F":
            return "color:#b91c1c;font-weight:700"
        return ""
    estilo = df.style
    return estilo.map(colorear) if hasattr(estilo, "map") else estilo.applymap(colorear)


# ---------------------------------------------------------------------------
# Callbacks (control de flujo)
# ---------------------------------------------------------------------------
def _ir_a_inicio() -> None:
    st.session_state["menu"] = "Inicio"


def _reiniciar_trivia() -> None:
    st.session_state.pop("trivia", None)


def _salir() -> None:
    st.session_state["salir"] = True


def _reabrir() -> None:
    st.session_state["salir"] = False


# ---------------------------------------------------------------------------
# Barra lateral (navegación)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Lógica Proposicional")
    st.radio("Módulo", list(PAGINAS), key="menu")
    st.caption("Variables permitidas: p, q, r (máx. 3)")
    st.button("Salir de la aplicación", on_click=_salir)

if st.session_state.get("salir"):
    st.success("Sesión cerrada. Puedes cerrar esta pestaña.")
    st.info("Para detener el servidor, presiona Ctrl+C en la terminal.")
    st.button("Volver a abrir la aplicación", on_click=_reabrir)
    st.stop()


# ---------------------------------------------------------------------------
# Página: Inicio
# ---------------------------------------------------------------------------
def pagina_inicio() -> None:
    st.title("Tablas de verdad, leyes lógicas y lógica proposicional")
    st.write("Aplicación de Matemáticas Discretas basada en la metodología "
             "**Pensar · Modelar · Codificar · Resolver**.")

    st.subheader("Notación aceptada")
    tabla = pd.DataFrame({
        "Operador": ["Negación", "Conjunción", "Disyunción",
                     "Implicación", "Bicondicional"],
        "Notaciones aceptadas": [
            "NOT, ~, ¬",
            "AND, &, ∧",
            "OR, |, ∨",
            "THEN, ->, →",
            "IFF, <->, ↔, =",
        ],
    })
    st.table(tabla)

    st.subheader("Reglas")
    st.markdown(
        "- Variables: `p`, `q`, `r` (máximo 3).\n"
        "- Longitud máxima: 80 caracteres y 12 conectivos.\n"
        "- Precedencia: `¬` > `∧` > `∨` > `→` > `↔`. Usa paréntesis para aclarar."
    )

    st.subheader("Módulos")
    st.markdown(
        "- **Tabla de verdad:** evalúa una expresión y clasifícala como tautología, "
        "contradicción o contingencia.\n"
        "- **A · Equivalencias:** compara dos expresiones e identifica la ley lógica.\n"
        "- **B · Trivia:** identifica leyes lógicas; sube de nivel con cada racha de aciertos."
    )
# ---------------------------------------------------------------------------
# Página: Tabla de verdad
# ---------------------------------------------------------------------------
def pagina_tabla() -> None:
    st.header("Tabla de verdad y evaluación")
    texto = st.text_input(
        "Escribe la expresión",
        placeholder="Ej.: (p AND q) -> r   ·   ~(p | q) = (~p & ~q)",
        key="tabla_expr",
    )
    completa = st.checkbox("Mostrar tabla de verdad completa", value=True,
                           key="tabla_completa")

    if not texto.strip():
        st.info("Escribe una expresión para comenzar.")
        return

    try:
        nodo = analizar(texto)
    except ErrorSintaxis as error:
        mostrar_error_sintaxis(error)
        return

    vars_ = ordenar_variables(variables_de(nodo))
    mostrar_formula(f"Forma normalizada: {a_texto(nodo)}")
    st.write(f"**Clasificación:** {clasificar(nodo)}")

    if completa:
        df = generar_tabla({"Resultado": nodo})
        st.dataframe(estilo_tabla(df), hide_index=True)
    else:
        st.markdown("**Evaluación con valores específicos**")
        columnas = st.columns(len(vars_))
        asignacion = {}
        for col, var in zip(columnas, vars_):
            asignacion[var] = col.selectbox(var, ["V", "F"], key=f"val_{var}") == "V"
        resultado = evaluar(nodo, asignacion)
        st.metric("Valor de verdad", "V" if resultado else "F")


# ---------------------------------------------------------------------------
# Página: Módulo A (equivalencias)
# ---------------------------------------------------------------------------
def pagina_equivalencias() -> None:
    st.header("Módulo A · Verificador de equivalencias")

    with st.form("form_equivalencias"):
        c1, c2 = st.columns(2)
        txt1 = c1.text_input("Expresión 1", placeholder="~(p AND q)")
        txt2 = c2.text_input("Expresión 2", placeholder="~p OR ~q")
        completa = st.checkbox("Mostrar tablas de verdad", value=True)
        enviar = st.form_submit_button("Verificar", type="primary")

    if not enviar:
        return

    nodos, errores = [], False
    for etiqueta, texto in (("Expresión 1", txt1), ("Expresión 2", txt2)):
        try:
            nodos.append(analizar(texto))
        except ErrorSintaxis as error:
            st.error(f"**{etiqueta}:** {error}")
            errores = True
    if errores:
        st.caption("Corrige la(s) expresión(es) y vuelve a verificar.")
        return
    n1, n2 = nodos

    mostrar_formula(f"E1: {a_texto(n1)}")
    mostrar_formula(f"E2: {a_texto(n2)}")

    if canonico(n1) == canonico(n2):
        st.success("Las expresiones son idénticas (reflexividad).")
    elif equivalentes(n1, n2):
        st.success("Son lógicamente equivalentes: sus tablas de verdad coinciden.")
        leyes = identificar_leyes(n1, n2)
        if leyes:
            st.markdown("**Ley(es) lógica(s) que se cumple(n):**")
            for ley in leyes:
                st.markdown(f"- **{ley}** → `{formula_ley(ley)}`")
        else:
            st.info("Son equivalentes, pero la transformación requiere varios pasos. "
                    "No coincide con una sola ley del catálogo.")
    else:
        st.error("No son equivalentes.")
        hallado = contraejemplo(n1, n2)
        if hallado:
            asig, v1, v2 = hallado
            desc = ", ".join(f"{v}={'V' if val else 'F'}" for v, val in asig.items())
            st.write(f"**Contraejemplo:** con {desc} → E1 = "
                     f"{'V' if v1 else 'F'}, E2 = {'V' if v2 else 'F'}.")

    if completa:
        df = generar_tabla({"E1": n1, "E2": n2, "E1 ↔ E2": ("iff", n1, n2)})
        st.dataframe(estilo_tabla(df), hide_index=True)


# ---------------------------------------------------------------------------
# Página: Módulo B (trivia)
# ---------------------------------------------------------------------------
def _estado_inicial_trivia() -> dict:
    return {
        "nivel": 1,
        "en_nivel": 0,
        "aciertos": 0,
        "total": 0,
        "racha": 0,
        "pregunta": generar_pregunta(1),
        "respondida": False,
        "ultima_correcta": False,
        "subio_nivel": False,
        "qid": 0,
    }


def _registrar_respuesta(t: dict, eleccion: str) -> None:
    correcta = eleccion == t["pregunta"]["ley"]
    t["respondida"] = True
    t["ultima_correcta"] = correcta
    t["total"] += 1
    t["subio_nivel"] = False
    if correcta:
        t["aciertos"] += 1
        t["racha"] += 1
        if t["nivel"] < NIVEL_MAXIMO:
            t["en_nivel"] += 1
            if t["en_nivel"] >= ACIERTOS_PARA_SUBIR:
                t["nivel"] += 1
                t["en_nivel"] = 0
                t["subio_nivel"] = True
    else:
        t["racha"] = 0


def pagina_trivia() -> None:
    st.header("Módulo B · Trivia de leyes lógicas")
    if "trivia" not in st.session_state:
        st.session_state["trivia"] = _estado_inicial_trivia()
    t = st.session_state["trivia"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nivel", f"{t['nivel']} · {NIVELES[t['nivel']][0]}")
    c2.metric("Aciertos", t["aciertos"])
    c3.metric("Racha", t["racha"])
    c4.metric("Progreso de nivel", f"{t['en_nivel']}/{ACIERTOS_PARA_SUBIR}")

    p = t["pregunta"]
    st.markdown("#### ¿Qué ley lógica relaciona estas dos expresiones?")
    mostrar_formula(f"{a_texto(p['e1'])}   ≡   {a_texto(p['e2'])}")

    if not t["respondida"]:
        with st.form(f"form_trivia_{t['qid']}"):
            eleccion = st.radio("Selecciona la ley correcta:", p["opciones"],
                                index=None, key=f"op_{t['qid']}")
            responder = st.form_submit_button("Responder", type="primary")
        if responder:
            if eleccion is None:
                st.warning("Selecciona una opción antes de responder.")
            else:
                _registrar_respuesta(t, eleccion)
                st.rerun()
    else:
        if t["ultima_correcta"]:
            st.success(f"¡Correcto! Es **{p['ley']}**.")
        else:
            st.error(f"Incorrecto. La ley correcta es **{p['ley']}**.")
        mostrar_formula(formula_ley(p["ley"]))
        if t["subio_nivel"]:
            st.success(f"¡Subiste al nivel {t['nivel']} · {NIVELES[t['nivel']][0]}!")
        if st.button("Siguiente pregunta ▶", type="primary"):
            t["pregunta"] = generar_pregunta(t["nivel"])
            t["respondida"] = False
            t["subio_nivel"] = False
            t["qid"] += 1
            st.rerun()

    st.divider()
    c_a, c_b = st.columns(2)
    c_a.button("Volver al menú principal", on_click=_ir_a_inicio,
               help="Tu progreso se conserva.")
    c_b.button("Terminar partida y reiniciar", on_click=_reiniciar_trivia)


# ---------------------------------------------------------------------------
# Enrutamiento
# ---------------------------------------------------------------------------
RUTAS = {
    "inicio": pagina_inicio,
    "tabla": pagina_tabla,
    "equivalencias": pagina_equivalencias,
    "trivia": pagina_trivia,
}
RUTAS[PAGINAS[st.session_state["menu"]]]()