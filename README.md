# Calculador de Valor Intrínseco (VMI)

App que reproduce el modelo de `VMI_Investing_template.xlsx` (hoja "VMI IV
Calculator (20 years)"): descuenta a 20 años el Ingreso Neto, el Flujo de
Caja Operativo o el Flujo de Caja Libre de una empresa para obtener su
**valor intrínseco por acción**.

Solo necesitas escribir el **stock symbol** — la app trae automáticamente
de Yahoo Finance los datos que en el Excel original ibas en las celdas de
fondo blanco (precio, deuda, caja, acciones en circulación, beta, etc.).
Los campos que Yahoo Finance no entrega (sobre todo las 3 tasas de
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

- Los datos financieros dependen de lo que Yahoo Finance tenga disponible
  para ese ticker; para algunas acciones (sobre todo fuera de EE. UU.)
  puede faltar algún dato — en ese caso el campo queda en 0 y debes
  llenarlo a mano.
- Las tasas de crecimiento a 5/10/20 años son supuestos de inversión, no
  datos verificables — la app solo te da un punto de partida (basado en el
  crecimiento histórico de utilidad neta) para que ejerzas tu propio
  criterio.
- La tasa de descuento se calcula como `Tasa libre de riesgo + Beta x Prima
  de riesgo de mercado`, igual que en el Excel original; puedes
  sobreescribirla directamente si prefieres otra.
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
- El motor de cálculo (`valuation.py`) fue validado contra los valores
  exactos que traía el archivo Excel original para Micron (MU): coincide
  hasta el décimo decimal.
