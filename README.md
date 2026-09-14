# Calculador de Valor Intrínseco (VMI)

App que calcula el **valor intrínseco por acción** de una empresa a partir
de un horizonte de **10 años**, en 3 tramos de crecimiento (el "Año 0" es el
año actual, sin crecer todavía):

- Años 1 a 3 → tasa de crecimiento 1
- Años 4 a 7 → tasa de crecimiento 2
- Años 8 a 10 → tasa de crecimiento 3
- Año 11 en adelante → **valor terminal** (perpetuidad de Gordon): se asume
  que a partir del año 11 el flujo crece para siempre a una tasa perpetua
  conservadora `g` (por defecto 2.5%), y ese valor se trae a valor presente
  y se suma al de los 10 años explícitos. Sin esto, acortar el horizonte de
  20 a 10 años simplemente "cortaría" 10 años de valor de la empresa sin
  compensarlo — el valor terminal es el ajuste estándar en valoración
  profesional para que un horizonte más corto siga siendo representativo.

Se descuenta el Ingreso Neto, el Flujo de Caja Operativo o el Flujo de Caja
Libre de la empresa (según el método elegido).

Solo necesitas escribir el **stock symbol** — la app trae automáticamente
de Yahoo Finance los datos que en el Excel original ibas en las celdas de
fondo blanco (precio, deuda, caja, acciones en circulación, beta, EBITDA,
etc.). Los campos que Yahoo Finance no entrega (sobre todo las 3 tasas de
crecimiento) quedan con un valor sugerido que puedes editar antes de
calcular.

## Instalación

Necesitas Python 3.9+ instalado. Luego, en una terminal:

```bash
cd vmi_app
pip install -r requirements.txt
```

## Ejecutar la app

```bash
streamlit run app.py
```

Se abrirá automáticamente en tu navegador (normalmente en
`http://localhost:8501`).

## Cómo se usa

1. Escribe el símbolo de la acción (ej. `AAPL`, `MU`, `0700.HK`).
2. Elige el método de valoración (Ingreso Neto / Flujo de Caja Operativo /
   Flujo de Caja Libre).
3. Presiona **"Traer datos y calcular"** — la app llena automáticamente los
   campos.
4. Revisa/ajusta los campos que quieras (especialmente las tasas de
   crecimiento a 5, 10 y 20 años, que son un supuesto tuyo, no un dato de
   mercado).
5. Presiona **"Calcular Valor Intrínseco"**.

Los dos resultados más importantes se muestran en tarjetas grandes:

- **Valor Intrínseco Final por Acción** — equivalente a la celda
  `N26` del Excel original.
- **Descuento / Prima** — equivalente a la celda `M28`: si es negativo
  (verde), la acción cotiza con **descuento** respecto a su valor
  intrínseco (potencialmente infravalorada); si es positivo (rojo), cotiza
  con **prima** (potencialmente sobrevalorada).

## Notas importantes

- **Crecimiento perpetuo (g)**: debe ser SIEMPRE menor a la tasa de
  descuento, o el cálculo del valor terminal no es matemáticamente válido
  (la app lo detecta y te avisa, usando $0 de valor terminal mientras tanto).
  Se recomienda un valor conservador (2%-3%, cercano al crecimiento de largo
  plazo de la economía) — nunca igual a la tasa de los años 8-10, que suele
  ser mucho más agresiva y no es sostenible para siempre.
- Es normal que el valor terminal represente una parte grande del valor
  total (60%-80% es típico) — así funciona este tipo de modelo, y por eso
  el supuesto de `g` es el que más cuidado merece.
- Los datos financieros dependen de lo que Yahoo Finance tenga disponible
  para ese ticker; para algunas acciones (sobre todo fuera de EE. UU.)
  puede faltar algún dato — en ese caso el campo queda en 0 y debes
  llenarlo a mano.
- Las tasas de crecimiento a 5/10/20 años son supuestos de inversión, no
  datos verificables — la app solo te da un punto de partida (basado en el
  crecimiento histórico de utilidad neta) para que ejerzas tu propio
  criterio.
- La tasa de descuento para acciones de **EE. UU.** se calcula con la tabla
  de referencia por Beta que definiste:

  | Beta | Tasa de descuento |
  |---|---|
  | Menor a 0.80 | 5.4% |
  | 1.0 | 6.0% |
  | 1.1 | 6.3% |
  | 1.2 | 6.6% |
  | 1.3 | 6.9% |
  | 1.4 | 7.2% |
  | 1.5 | 7.5% |
  | Mayor a 1.6 | 7.8% |

  La búsqueda es por escalón (como un `VLOOKUP` aproximado): se usa la tasa
  del punto de la tabla igual o inmediatamente inferior al Beta real de la
  acción (sin interpolar). Para acciones de **China/Hong Kong** se mantiene
  la fórmula `Tasa libre de riesgo + Beta x Prima de riesgo de mercado`, ya
  que no se definió una tabla equivalente para esa región.
- Para acciones de EE. UU., la **Prima de riesgo de mercado (ERP)** y la
  **Tasa libre de riesgo (Rf)** se traen automáticamente de la guía vigente
  más reciente ("Current Guidance") que publica **Kroll** (antes Duff &
  Phelps) — el estándar más usado en valoración profesional en EE. UU. La
  página web de Kroll solo muestra el valor actual en un gráfico SVG (no
  legible por código), así que la app lee directamente la tabla histórica en
  PDF que Kroll publica junto a esa página, y toma su primera fila ("UNTIL
  FURTHER NOTICE" = la vigencia actual). Si no hay conexión, la app usa un
  valor de respaldo y te avisa. Para acciones de China/Hong Kong se mantiene
  el valor de referencia original del Excel (Kroll no cubre esa región en
  esta tabla).
- Nota de Kroll: si el rendimiento *spot* del bono del Tesoro a 20 años es
  mayor a la tasa "normalizada" que trae la tabla, ellos recomiendan usar
  ese valor spot en su lugar. La app no lo calcula automáticamente — puedes
  ajustar el campo "Tasa libre de riesgo" a mano si aplica.
- **Montos en millones**: cualquier cifra en dólares o cantidad de acciones
  mayor a 1,000,000 se muestra (y se edita) en millones, sin decimales, para
  que no tengas que leer una fila de ceros. La app la vuelve a convertir a
  unidades absolutas antes de calcular, así que el resultado no cambia.
- **Opinión de analistas**: la app trae automáticamente de Yahoo Finance el
  precio objetivo promedio, el rango (mínimo–máximo), cuántos analistas
  cubren la acción, y la recomendación de consenso (Compra Fuerte / Compra /
  Mantener / Venta / Venta Fuerte). Se muestra como una tercera tarjeta junto
  a tus resultados, con el % de upside/downside respecto al último cierre, y
  una comparación directa: Último cierre vs. tu Valor Intrínseco vs. Precio
  Objetivo de Analistas. Si el ticker no tiene cobertura de analistas, la
  tarjeta lo indica en vez de fallar.
  ⚠️ Los precios objetivo de analistas tienen sesgos conocidos (tienden a
  ser optimistas y a rezagarse ante cambios de tendencia) — trátalos como
  contexto complementario, no como validación de tu modelo.
- **Ratio P/E (Precio/Beneficio TTM)**: se muestra con un decimal junto al
  indicador de apalancamiento (ej. "24.6x"). Viene directo de Yahoo Finance
  (`trailingPE`); si no está disponible para el ticker, se muestra "N/D".
- **Indicador de apalancamiento (Deuda Total / EBITDA)**: se calcula como
  `Deuda total / EBITDA del último período`. Interpretación:
  menor a 2x = Excelente, entre 2x y 4x = Saludable, entre 4x y 5x =
  Alerta, mayor a 5x = Riesgosa. Si Yahoo Finance no reporta el EBITDA para
  ese ticker, el indicador queda como "No disponible".
- Las celdas **"Último cierre"** y **"Tasa de descuento"** aparecen con un
  resaltado leve (fondo amarillo claro) porque son las dos que más conviene
  revisar antes de calcular.
- El motor de cálculo (`valuation.py`) fue validado contra los valores
  exactos que traía el archivo Excel original para Micron (MU): coincide
  hasta el décimo decimal.
