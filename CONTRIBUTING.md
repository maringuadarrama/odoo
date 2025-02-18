# Guía de Estilo para Código Odoo - AgroMarin

En AgroMarin, la estandarización de las prácticas de desarrollo en Odoo es fundamental para garantizar la calidad, mantenibilidad y escalabilidad de nuestras soluciones tecnológicas. Esta guía tiene como objetivo establecer un conjunto de normas claras y consistentes que aseguren un código limpio, alineado con los estándares de la comunidad (OCA) y adaptado a los requisitos específicos de nuestra organización.

Actualmente, la falta de uniformidad en la estructura de módulos nativos, convenciones de código y documentación ha generado inconsistencias que dificultan la colaboración entre equipos y limitan la eficiencia en el desarrollo. Con esta guía, buscamos resolver estos desafíos, promoviendo buenas prácticas que faciliten la integración de nuevos desarrolladores, mejoren la calidad del software y optimicen los procesos de mantenimiento y escalabilidad.

## Base de referencia:

AgroMarin adopta los estándares oficiales de la [OCA (Odoo Community Association)](https://github.com/OCA/maintainer-tools/blob/master/CONTRIBUTING.md) y las guías de desarrollo de [Odoo](https://www.odoo.com/documentation/18.0/es_419/contributing/development/coding_guidelines.html) como punto de partida. Estos lineamientos cubren aspectos clave del desarrollo, incluyendo:

**Python:**
- Convenciones de nombres (snake_case para variables y métodos).
- Uso adecuado de decoradores (@api.model, @api.depends, etc.).
- Estructuración de modelos y métodos.

**XML:**
- Definición de vistas, menús y acciones.
- Uso de xpath para personalizaciones.
- Buenas prácticas en la organización de archivos XML.

**JavaScript:**
- Convenciones de nombres (camelCase para variables y funciones).
- Uso de use strict para evitar errores comunes.
- Modularización del código (widgets, servicios, etc.).

**Estructura de Módulos:**
- Organización de carpetas (models, views, controllers, etc.).
- Nombres descriptivos para archivos y directorios.

## Estandares AgroMarin

### Declaración de Campos

Los campos deben declararse en el siguiente **orden obligatorio** (según la proporción de mayor a menor frecuencia de uso): **Char, Integer, Float, Boolean, Date, Datetime, Binary, Image, Selection, Html, Text, Many2one, One2many, Many2many, Monetary, Related, Computed, Reference**. Cada bloque de campos debe ir precedido por un comentario que indique el tipo de campo, mejorando la legibilidad y facilitando la identificación rápida.

**Ejemplo correcto:**
```python
class ExampleModel(models.Model):

    # Char
    name = fields.Char(string="Referencia", required=True)

    # Integer
    priority = fields.Integer(default=1)

    # Float
    total_weight = fields.Float(digits=(12, 2))

    # Boolean
    is_urgent = fields.Boolean()

    # Date
    date_planned = fields.Date()

    # Selection
    state = fields.Selection([("draft", "Borrador"), ("done", "Confirmado")])

    # Many2one
    partner_id = fields.Many2one("res.partner")

    # One2many
    line_ids = fields.One2many("agromarin.purchase.line", "order_id")

    # Computed
    total_amount = fields.Float(compute="_compute_total")
```

**Ejemplo incorrecto:**
```python
class ExampleModel(models.Model):
    _name = "example.model"

    # Char
    name = fields.Char(string="Referencia", required=True)

    # Integer
    priority = fields.Integer(default=1)

    # Float
    total_weight = fields.Float(digits=(12, 2))
    total_amount = fields.Float(compute="_compute_total")  # Debe ir precedido de Computed y esta Fuera de orden

    # Many2one
    partner_id = fields.Many2one("res.partner")

    # One2many
    line_ids = fields.One2many("agromarin.purchase.line", "order_id")

    # Boolean
    is_urgent = fields.Boolean()  # Fuera de orden

    # Date
    date_planned = fields.Date()  # Fuera de orden

    # Selection
    state = fields.Selection([("draft", "Borrador"), ("done", "Confirmado")])

```

### Categorizacion de métodos

- *Constructores:* métodos provenientes de Models.model (ej: `create`, `write`, `unlink`, `copy` ).

- *Computados / Onchange:* métodos que usen decoradores api.depends y/o api.onchange, primero deben ir los calculados y luegos los onchange, deben organizarse de menos a mas dependencias como primer criterio y por su campo dependiente como segundo criterio de ordenamiento.

- *Validaciones:* métodos que evalúan una condición y que devuelven un booleano o un mensaje de error, con prefijo "_check" o "_validate", en la algunos casos usan el decorador api.constrains

- *Acciones:* métodos que son llamados desde botones, con prefijo "action".

- *Lógica de negocio:* métodos que realizan un flujo de trabajo, con prefijo `_do`, pero puede variar en algunos casos (ej: `_post` en asientos contables)

- *Helpers:* métodos internos usado para preprocesamiento, con prefijo `_get`, `_prepare`, `_find_`

- *Tools:* métodos re-utilizables sin dependencia del objeto (ej: `format_currency`, `send_notification`)

- *Integraciones:* métodos que interactúan con APIs externas.

- *Otros:* no aplica ninguno de los anteriores

**Ejemplo correcto:**
```python
class ExampleModel(models.Model):

    # Constructores
    @api.model
    def create(self, vals):
    ...

    # Computados
    @api.depends("line_ids.price")
    def _compute_total(self):
    ...

    # Validaciones
    @api.constrains("date")
    def _check_date(self):
    ...

    # Acciones
    def action_confirm(self):
    ...

    # Logica de negocio
    def _post(self):
    ...


    # Helpers
    def _get_discount_policy(self):
    ...

    # Tools
    def format_agromarin_code(self):
    ...

    # Integraciones
    def _call_api_agriculture(self):
    ...

```

**Ejemplo incorrecto:**
```python
class ExampleModel(models.Model):

    # Constructores
    @api.model
    def create(self, vals):
    ...

    # Computados
    @api.depends("line_ids.price")
    def _compute_total(self):
    ...

    @api.constrains("date")
    def _check_date(self):
    ...

    # Logica de negocio
    def _post(self):
    ...

    # Helpers
    def _get_discount_policy(self):
    ...

    # Tools
    def format_agromarin_code(self):
    ...

    def _call_api_agriculture(self):
    ...

    # Acciones
    def action_confirm(self):
    ...

```

En el ejemplo incorrecto, aunque el orden de las categorías no es estrictamente fijo, hay errores en la clasificación de ciertos métodos.

- El método `_check_date` está colocado dentro de la categoría de Computados, cuando en realidad debería estar en Validaciones.
- El método `_call_api_agriculture` fue clasificado como Tools, cuando pertenece a Integraciones.

Para una correcta categorización, es fundamental asignar cada método a su categoría correspondiente y, además, considerar la precedencia entre ellos. Por ejemplo, si el método A realiza internamente un llamado al método B, el método B debe ser declarado antes que el método A.

**Ejemplo correcto:**
```python
class ExampleModel(models.Model):

    # Helpers
    def _calculate_discount(self):
        """Método auxiliar usado en otros métodos"""
        return 10

    # Lógica de negocio
    def _compute_total_price(self):
        """Método que usa _calculate_discount"""
        discount = self._calculate_discount()
        self.total_price = self.subtotal - discount

    # Acciones
    def action_confirm(self):
        """Método que usa _compute_total_price"""
        self._compute_total_price()
        self.state = "confirmed"
```

**Ejemplo incorrecto:**
```python
class ExampleModel(models.Model):

    # Lógica de negocio
    def _compute_total_price(self):
        """Método que usa _calculate_discount"""
        discount = self._calculate_discount() 
        self.total_price = self.subtotal - discount

    # Helpers
    def _calculate_discount(self):
        """Método auxiliar usado en otros métodos"""
        return 10

    # Acciones
    def action_confirm(self):
        """Método que usa _compute_total_price"""
        self._compute_total_price()
        self.state = "confirmed"
```

### Uniformidad en el uso de comillas
Se debe utilizar comillas dobles (""") en los siguientes casos:

- **Docstrings** (clases, métodos y funciones).
- **Atributos en la declaración de campos** en modelos de datos.
- **Cadenas de caracteres** en el código

**Ejemplo correcto:**
```python
class ExampleModel(models.Model):
    """Modelo de ejemplo que representa una entidad."""

    name = fields.Char(string="Nombre")  # Se usan comillas dobles en los atributos
    description = fields.Text(string="Descripción")

    def get_greeting(self):
        """Retorna un saludo personalizado."""
        return f"Hola, {self.name}"

```

**Ejemplo incorrecto:**
```python
class ExampleModel(models.Model):
    '''Modelo de ejemplo que representa una entidad.'''  # Comillas simples en docstring de la clase

    name = fields.Char(string='Nombre')  # Comillas simples en los atributos
    description = fields.Text(string='Descripción')

    def get_greeting(self):
        '''Retorna un saludo personalizado.'''  # Comillas simples en docstring del método
        return f'Hola, {self.name}'  # Comillas simples en una cadena de caracteres

```

### Claridad y mantenibilidad
Para garantizar claridad y mantenibilidad del código, se hace obligatorio el uso de **docstrings** en:

- **Modelos** (describir el propósito de la clase).
- **Métodos complejos** (incluir descripción, parámetros y retornos).
- **Funciones auxiliares críticas** que afecten la lógica del sistema.

**Ejemplo correcto:**
```python
class ExampleModel(models.Model):
    """Modelo que gestiona los registros de ejemplo."""

    name = fields.Char(string="Nombre")
    age = fields.Integer(string="Edad")

    def calculate_discount(self, price: float) -> float:
        """
        Calcula un descuento del 10% sobre un precio dado.

        :param float price: Precio original antes del descuento.
        :return: Precio con el descuento aplicado.
        :rtype: float
        """
        discount = price * 0.10
        return price - discount
```

**Ejemplo incorrecto:**
```python
class ExampleModel(models.Model):
    # Modelo que maneja registros
    name = fields.Char(string="Nombre")
    age = fields.Integer(string="Edad")

    def calculate_discount(self, price):
        # Calcula descuento
        return price - (price * 0.10)
```

Errores en el ejemplo incorrecto:
- Falta de docstrings en la clase y el método.
- Comentarios vagos que no explican el propósito de la función ni los parámetros.

**Plantilla obligatoria para docstrings**

Los docstrings son esenciales para documentar el propósito, parámetros y comportamiento de métodos y modelos. En AgroMarin, se requiere el uso de una plantilla estándar para garantizar que la documentación sea clara, consistente y útil para todos los desarrolladores. Esta plantilla debe incluir los siguientes elementos:

- *Descripción General:* Explicar brevemente el propósito del método o modelo. Si es un modelo, describir su función principal y los campos clave.

- *Parámetros (si aplica):* Listar y describir cada parámetro que recibe el método. Especificar el tipo de dato y su propósito.

- *Retornos (si aplica):* Describir lo que devuelve el método (tipo de dato y significado).

```python
class AgroMarinInvoice(models.Model):
    """Modelo para gestionar facturas de AgroMarin

    Campos:
        partner_id (res.partner): Cliente asociado
        date_invoice (Date): Fecha de emisión
    """

    def action_validate(self):
        """Valida la factura y genera asientos contables

        Parámetros:
            context (dict): Contexto de la operación

        Retorna:
            bool: True si la validación fue exitosa
        """

        # Lógica aquí
```
