"""
logica.py — Núcleo lógico de la aplicación (independiente de la interfaz).

Contiene:
  * Tokenizador: acepta notación formal y texto plano.
  * Parser recursivo descendente con validación sintáctica (ErrorSintaxis).
  * Evaluador, tablas de verdad y clasificación de fórmulas.
  * Verificador de equivalencias y catálogo de leyes lógicas.
  * Generador de preguntas para el juego de trivia (niveles progresivos).
"""
from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------------------
# Configuración general
# ---------------------------------------------------------------------------
VARIABLES_PERMITIDAS = ("p", "q", "r")   # máximo 3 variables proposicionales
MAX_VARIABLES = 3
MAX_CARACTERES = 80                      # longitud máxima de la expresión
MAX_CONECTIVOS = 12                      # evita anidamientos excesivos
ACIERTOS_PARA_SUBIR = 3                  # aciertos por nivel en la trivia
NIVEL_MAXIMO = 5


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class ErrorSintaxis(Exception):
    """Error de sintaxis con mensaje legible y posición (opcional)."""

    def __init__(self, mensaje: str, posicion: int | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.posicion = posicion

    def __str__(self) -> str:
        if self.posicion is None:
            return self.mensaje
        return f"{self.mensaje} (posición {self.posicion + 1})"

# ---------------------------------------------------------------------------
# 1. Tokenizador
# ---------------------------------------------------------------------------
SIMBOLOS = {
    "¬": "NOT", "~": "NOT",
    "∧": "AND", "&": "AND",
    "∨": "OR", "|": "OR",
    "→": "THEN", "->": "THEN",
    "↔": "IFF", "<->": "IFF", "=": "IFF",
}
# Palabras y frases en minúsculas, en inglés y español
PALABRAS = {
    # inglés
    "not": "NOT", "and": "AND", "or": "OR",
    "then": "THEN", "implies": "THEN", "iff": "IFF",
    # español
    "no": "NOT", "y": "AND", "o": "OR",
    "entonces": "THEN", "implica": "THEN",
    "sii": "IFF",
}
# Frases de varias palabras (se buscan antes que las palabras sueltas)
FRASES = {
    "si y solo si": "IFF",
    "si entonces": "THEN",
}
OPERADORES = {"NOT", "AND", "OR", "THEN", "IFF"}
TOKEN_RE = re.compile(r"<->|->|[↔→¬~∧∨&|=()]|[A-Za-z]+|(\S)")


@dataclass(frozen=True)
class Token:
    tipo: str    # VAR, NOT, AND, OR, THEN, IFF, LP, RP
    texto: str   # texto original tal como lo escribió el usuario
    pos: int     # posición en la cadena original


def tokenizar(texto: str) -> list[Token]:
    """Convierte la cadena en tokens. Lanza ErrorSintaxis ante algo no reconocido."""
    tokens: list[Token] = []
    i = 0
    while i < len(texto):
        if texto[i].isspace():
            i += 1
            continue

        # 1) Frases de varias palabras
        frase_hallada = False
        for frase, tipo in FRASES.items():
            fragmento = texto[i:i + len(frase)]
            siguiente = texto[i + len(frase):i + len(frase) + 1]
            if (" ".join(fragmento.lower().split()) == frase
                    and (siguiente == "" or not siguiente.isalpha())):
                tokens.append(Token(tipo, fragmento, i))
                i += len(frase)
                frase_hallada = True
                break
        if frase_hallada:
            continue

        # 2) Símbolos y palabras sueltas
        m = TOKEN_RE.match(texto, i)
        lexema, pos = m.group(0), i
        i = m.end()
        if m.group(1) is not None:
            raise ErrorSintaxis(f"Carácter no reconocido: '{lexema}'", pos)
        if lexema == "(":
            tokens.append(Token("LP", lexema, pos))
        elif lexema == ")":
            tokens.append(Token("RP", lexema, pos))
        elif lexema in SIMBOLOS:
            tokens.append(Token(SIMBOLOS[lexema], lexema, pos))
        else:
            clave = lexema.lower()
            if clave in PALABRAS:
                tokens.append(Token(PALABRAS[clave], lexema, pos))
            elif clave in VARIABLES_PERMITIDAS:
                tokens.append(Token("VAR", clave, pos))
            elif clave == "si":
                raise ErrorSintaxis(
                    "'si' debe escribirse como 'si ... entonces' o 'si y solo si'", pos)
            else:
                raise ErrorSintaxis(
                    f"'{lexema}' no es una variable ni un conectivo válido. "
                    "Usa p, q, r y los conectivos de la tabla de notación.", pos)
    return tokens

# ---------------------------------------------------------------------------
# 2. Parser recursivo descendente
# ---------------------------------------------------------------------------
class _Parser:
    """
    Gramática (de menor a mayor precedencia):

        bicond := impl  ( IFF impl )*
        impl   := disj  ( THEN impl )?        -> asociativa a la derecha
        disj   := conj  ( OR conj )*
        conj   := unario ( AND unario )*
        unario := NOT unario | atomo
        atomo  := VAR | '(' bicond ')'

    Nodos del AST: ('var', nombre), ('not', a), ('and', a, b),
                   ('or', a, b), ('then', a, b), ('iff', a, b)
    """

    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._i = 0

    def _actual(self) -> Token | None:
        return self._tokens[self._i] if self._i < len(self._tokens) else None

    def _avanzar(self) -> Token:
        tok = self._tokens[self._i]
        self._i += 1
        return tok

    def parsear(self):
        if not self._tokens:
            raise ErrorSintaxis("La expresión está vacía.")
        nodo = self._bicond()
        resto = self._actual()
        if resto is not None:
            if resto.tipo == "RP":
                raise ErrorSintaxis("Paréntesis ')' sin abrir.", resto.pos)
            if resto.tipo == "NOT":
                raise ErrorSintaxis(
                    "Negación mal colocada: 'NOT' debe ir antes de un operando, "
                    "no después de uno.", resto.pos)
            raise ErrorSintaxis(f"Símbolo inesperado '{resto.texto}'.", resto.pos)
        return nodo

    def _bicond(self):
        izq = self._impl()
        while self._actual() and self._actual().tipo == "IFF":
            self._avanzar()
            izq = ("iff", izq, self._impl())
        return izq

    def _impl(self):
        izq = self._disj()
        if self._actual() and self._actual().tipo == "THEN":
            self._avanzar()
            return ("then", izq, self._impl())
        return izq

    def _disj(self):
        izq = self._conj()
        while self._actual() and self._actual().tipo == "OR":
            self._avanzar()
            izq = ("or", izq, self._conj())
        return izq

    def _conj(self):
        izq = self._unario()
        while self._actual() and self._actual().tipo == "AND":
            self._avanzar()
            izq = ("and", izq, self._unario())
        return izq

    def _unario(self):
        tok = self._actual()
        if tok and tok.tipo == "NOT":
            self._avanzar()
            return ("not", self._unario())
        return self._atomo()

    def _atomo(self):
        tok = self._actual()
        if tok is None:
            raise ErrorSintaxis("Falta un operando al final de la expresión.")
        if tok.tipo == "VAR":
            self._avanzar()
            return ("var", tok.texto)
        if tok.tipo == "LP":
            self._avanzar()
            nodo = self._bicond()
            cierre = self._actual()
            if cierre is None or cierre.tipo != "RP":
                raise ErrorSintaxis("Falta cerrar un paréntesis ')'.", tok.pos)
            self._avanzar()
            return nodo
        if tok.tipo == "RP":
            raise ErrorSintaxis(
                "Paréntesis vacío o mal ubicado: falta un operando antes de ')'.",
                tok.pos)
        raise ErrorSintaxis(
            f"Se esperaba una variable, una negación o '(' antes de '{tok.texto}'.",
            tok.pos)


def analizar(texto: str):
    """
    Valida la sintaxis y devuelve el árbol sintáctico (AST).
    Lanza ErrorSintaxis con un mensaje claro si algo no es válido.
    """
    if texto is None or not texto.strip():
        raise ErrorSintaxis("La expresión está vacía.")
    if len(texto.strip()) > MAX_CARACTERES:
        raise ErrorSintaxis(
            f"La expresión supera los {MAX_CARACTERES} caracteres permitidos.")
    tokens = tokenizar(texto)
    if sum(t.tipo in OPERADORES for t in tokens) > MAX_CONECTIVOS:
        raise ErrorSintaxis(f"Demasiados conectivos: el máximo es {MAX_CONECTIVOS}.")
    nodo = _Parser(tokens).parsear()
    if len(variables_de(nodo)) > MAX_VARIABLES:
        raise ErrorSintaxis(f"Máximo {MAX_VARIABLES} variables proposicionales.")
    return nodo


# ---------------------------------------------------------------------------
# 3. Utilidades sobre el AST
# ---------------------------------------------------------------------------
BINARIOS = {"and", "or", "then", "iff"}
BINARIOS_CONMUTATIVOS = {"and", "or", "iff"}
PRECEDENCIA = {"var": 6, "meta": 6, "not": 5, "and": 4, "or": 3, "then": 2, "iff": 1}
SIMBOLO_NODO = {"not": "¬", "and": "∧", "or": "∨", "then": "→", "iff": "↔"}


def a_texto(n) -> str:
    """Convierte un AST en texto con paréntesis solo cuando hacen falta."""
    if n[0] in ("var", "meta"):
        return n[1]
    if n[0] == "not":
        hijo = a_texto(n[1])
        if n[1][0] in BINARIOS:
            hijo = f"({hijo})"
        return f"¬{hijo}"
    izq, der = n[1], n[2]
    s_izq, s_der = a_texto(izq), a_texto(der)
    prec = PRECEDENCIA[n[0]]
    if PRECEDENCIA[izq[0]] <= prec:
        s_izq = f"({s_izq})"
    if PRECEDENCIA[der[0]] <= prec:
        s_der = f"({s_der})"
    return f"{s_izq} {SIMBOLO_NODO[n[0]]} {s_der}"


def variables_de(n) -> set[str]:
    if n[0] == "var":
        return {n[1]}
    return set().union(*(variables_de(h) for h in n[1:]))


def ordenar_variables(vs) -> list[str]:
    return [v for v in VARIABLES_PERMITIDAS if v in vs]


def evaluar(n, asignacion: dict[str, bool]) -> bool:
    t = n[0]
    if t == "var":
        return asignacion[n[1]]
    if t == "not":
        return not evaluar(n[1], asignacion)
    a = evaluar(n[1], asignacion)
    b = evaluar(n[2], asignacion)
    if t == "and":
        return a and b
    if t == "or":
        return a or b
    if t == "then":
        return (not a) or b
    if t == "iff":
        return a == b
    raise ValueError(f"Nodo desconocido: {t}")


def filas_verdad(variables):
    """Genera todas las asignaciones (primera fila: todo V, como en los libros)."""
    for valores in itertools.product((True, False), repeat=len(variables)):
        yield dict(zip(variables, valores))


def canonico(n):
    """Forma canónica: ordena operandos de los conectivos conmutativos."""
    if n[0] == "var":
        return n
    if n[0] == "not":
        return ("not", canonico(n[1]))
    izq, der = canonico(n[1]), canonico(n[2])
    if n[0] in BINARIOS_CONMUTATIVOS and a_texto(der) < a_texto(izq):
        izq, der = der, izq
    return (n[0], izq, der)


def equivalentes(e1, e2) -> bool:
    vars_ = sorted(variables_de(e1) | variables_de(e2))
    return all(evaluar(e1, a) == evaluar(e2, a) for a in filas_verdad(vars_))


def contraejemplo(e1, e2):
    """Devuelve (asignación, valor_e1, valor_e2) de la primera fila que difiere, o None."""
    vars_ = ordenar_variables(variables_de(e1) | variables_de(e2))
    for asig in filas_verdad(vars_):
        v1, v2 = evaluar(e1, asig), evaluar(e2, asig)
        if v1 != v2:
            return asig, v1, v2
    return None


def clasificar(nodo) -> str:
    valores = {evaluar(nodo, a)
               for a in filas_verdad(ordenar_variables(variables_de(nodo)))}
    if valores == {True}:
        return "Tautología (V en todas las filas)"
    if valores == {False}:
        return "Contradicción (F en todas las filas)"
    return "Contingencia (V en algunas filas y F en otras)"


def generar_tabla(expresiones: dict) -> pd.DataFrame:
    """Tabla de verdad con columnas de variables y una columna por expresión."""
    vars_ = ordenar_variables(
        set().union(*(variables_de(n) for n in expresiones.values())))
    filas = []
    for asig in filas_verdad(vars_):
        fila = {v: ("V" if asig[v] else "F") for v in vars_}
        for nombre, nodo in expresiones.items():
            fila[nombre] = "V" if evaluar(nodo, asig) else "F"
        filas.append(fila)
    return pd.DataFrame(filas, columns=vars_ + list(expresiones.keys()))


# ---------------------------------------------------------------------------
# 4. Catálogo de leyes lógicas y verificador de equivalencias
# ---------------------------------------------------------------------------
# Metavariables (patrones): sustituibles por cualquier subexpresión.
def M(nombre): return ("meta", nombre)
def NEG(a): return ("not", a)
def CONJ(a, b): return ("and", a, b)
def DISJ(a, b): return ("or", a, b)
def IMPL(a, b): return ("then", a, b)
def BICOND(a, b): return ("iff", a, b)


A, B, C = M("A"), M("B"), M("C")

LEYES = [
    ("Doble negación", NEG(NEG(A)), A),
    ("Conmutativa de ∧", CONJ(A, B), CONJ(B, A)),
    ("Conmutativa de ∨", DISJ(A, B), DISJ(B, A)),
    ("Conmutativa de ↔", BICOND(A, B), BICOND(B, A)),
    ("Asociativa de ∧", CONJ(CONJ(A, B), C), CONJ(A, CONJ(B, C))),
    ("Asociativa de ∨", DISJ(DISJ(A, B), C), DISJ(A, DISJ(B, C))),
    ("Idempotencia de ∧", CONJ(A, A), A),
    ("Idempotencia de ∨", DISJ(A, A), A),
    ("Leyes de De Morgan (∧)", NEG(CONJ(A, B)), DISJ(NEG(A), NEG(B))),
    ("Leyes de De Morgan (∨)", NEG(DISJ(A, B)), CONJ(NEG(A), NEG(B))),
    ("Distributiva de ∧ sobre ∨", CONJ(A, DISJ(B, C)), DISJ(CONJ(A, B), CONJ(A, C))),
    ("Distributiva de ∨ sobre ∧", DISJ(A, CONJ(B, C)), CONJ(DISJ(A, B), DISJ(A, C))),
    ("Absorción (∧)", CONJ(A, DISJ(A, B)), A),
    ("Absorción (∨)", DISJ(A, CONJ(A, B)), A),
    ("Definición de implicación", IMPL(A, B), DISJ(NEG(A), B)),
    ("Contrapositiva", IMPL(A, B), IMPL(NEG(B), NEG(A))),
    ("Exportación", IMPL(CONJ(A, B), C), IMPL(A, IMPL(B, C))),
    ("Negación de la implicación", NEG(IMPL(A, B)), CONJ(A, NEG(B))),
    ("Equivalencia como doble implicación", BICOND(A, B),
     CONJ(IMPL(A, B), IMPL(B, A))),
    ("Equivalencia como disyunción de conjunciones", BICOND(A, B),
     DISJ(CONJ(A, B), CONJ(NEG(A), NEG(B)))),
]
LEY_POR_NOMBRE = {nombre: (lhs, rhs) for nombre, lhs, rhs in LEYES}


def formula_ley(nombre: str) -> str:
    lhs, rhs = LEY_POR_NOMBRE[nombre]
    return f"{a_texto(lhs)} ≡ {a_texto(rhs)}"


def _emparejar(patron, nodo, ligaduras: dict):
    """Intenta unificar un patrón con un nodo. Devuelve ligaduras o None."""
    if patron[0] == "meta":
        nombre = patron[1]
        if nombre in ligaduras:
            ok = canonico(ligaduras[nombre]) == canonico(nodo)
            return ligaduras if ok else None
        nuevas = dict(ligaduras)
        nuevas[nombre] = nodo
        return nuevas
    if patron[0] != nodo[0]:
        return None
    if patron[0] == "not":
        return _emparejar(patron[1], nodo[1], ligaduras)
    opciones = [(nodo[1], nodo[2])]
    if patron[0] in BINARIOS_CONMUTATIVOS:           # probar también el orden inverso
        opciones.append((nodo[2], nodo[1]))
    for izq, der in opciones:
        r = _emparejar(patron[1], izq, ligaduras)
        if r is not None:
            r = _emparejar(patron[2], der, r)
            if r is not None:
                return r
    return None


def _instanciar(patron, ligaduras: dict):
    """Sustituye las metavariables. Devuelve None si alguna quedó sin ligar."""
    if patron[0] == "meta":
        return ligaduras.get(patron[1])
    partes = [_instanciar(h, ligaduras) for h in patron[1:]]
    if any(p is None for p in partes):
        return None
    return (patron[0],) + tuple(partes)


def identificar_leyes(e1, e2) -> list[str]:
    """Nombres de las leyes del catálogo que justifican e1 ≡ e2 en un paso."""
    hallados: list[str] = []
    for x, y in ((e1, e2), (e2, e1)):
        for nombre, lhs, rhs in LEYES:
            for patron, resultado in ((lhs, rhs), (rhs, lhs)):
                lig = _emparejar(patron, x, {})
                if lig is None:
                    continue
                inst = _instanciar(resultado, lig)
                if inst is not None and canonico(inst) == canonico(y):
                    if nombre not in hallados:
                        hallados.append(nombre)
    return hallados


# ---------------------------------------------------------------------------
# 5. Generador de preguntas para la trivia
# ---------------------------------------------------------------------------
_BASICAS = [
    "Doble negación", "Conmutativa de ∧", "Conmutativa de ∨",
    "Idempotencia de ∧", "Idempotencia de ∨",
    "Leyes de De Morgan (∧)", "Leyes de De Morgan (∨)",
]
_INTERMEDIAS = _BASICAS + [
    "Distributiva de ∧ sobre ∨", "Distributiva de ∨ sobre ∧",
    "Definición de implicación", "Contrapositiva",
]
_AVANZADAS = _INTERMEDIAS + [
    "Absorción (∧)", "Absorción (∨)", "Exportación",
    "Negación de la implicación", "Asociativa de ∧", "Asociativa de ∨",
]
_EXPERTAS = _AVANZADAS + [
    "Equivalencia como doble implicación",
    "Equivalencia como disyunción de conjunciones", "Conmutativa de ↔",
]

# nivel -> (nombre, leyes disponibles, profundidad de subexpresiones, envolver en contexto)
NIVELES = {
    1: ("Básico", _BASICAS, 0, False),
    2: ("Intermedio", _INTERMEDIAS, 1, False),
    3: ("Avanzado", _AVANZADAS, 1, False),
    4: ("Experto", _EXPERTAS, 2, False),
    5: ("Maestro", _EXPERTAS, 2, True),   # la ley se aplica dentro de una expresión mayor
}


def _sustituto(profundidad: int):
    """Genera una subexpresión aleatoria de la profundidad indicada."""
    if profundidad <= 0 or random.random() < 0.35:
        var = ("var", random.choice(VARIABLES_PERMITIDAS))
        return ("not", var) if random.random() < 0.3 else var
    tipo = random.choice(["and", "or", "then", "iff", "not"])
    if tipo == "not":
        return ("not", _sustituto(profundidad - 1))
    return (tipo, _sustituto(profundidad - 1), _sustituto(profundidad - 1))


def generar_pregunta(nivel: int, intentos: int = 60) -> dict:
    """
    Crea una pregunta: dos expresiones equivalentes, la ley correcta y 4 opciones.
    Garantiza que la ley correcta sea la única que justifica el par (sin ambigüedad).
    """
    nombre_nivel, pool, profundidad, con_contexto = NIVELES[nivel]
    objetivo = random.choice(pool)
    e1 = e2 = None
    for _ in range(intentos):
        objetivo = random.choice(pool)
        lhs, rhs = LEY_POR_NOMBRE[objetivo]
        lig = {m: _sustituto(profundidad) for m in ("A", "B", "C")}
        e1, e2 = _instanciar(lhs, lig), _instanciar(rhs, lig)
        if canonico(e1) != canonico(e2) and set(identificar_leyes(e1, e2)) == {objetivo}:
            break

    if con_contexto:                       # la ley se aplica dentro de una expresión mayor
        contexto = _sustituto(1)
        op = random.choice(("and", "or"))
        e1, e2 = (op, contexto, e1), (op, contexto, e2)

    distractores = random.sample([ley for ley in pool if ley != objetivo], 3)
    opciones = distractores + [objetivo]
    random.shuffle(opciones)
    return {
        "nivel": nivel,
        "nombre_nivel": nombre_nivel,
        "e1": e1,
        "e2": e2,
        "ley": objetivo,
        "opciones": opciones,
    }
