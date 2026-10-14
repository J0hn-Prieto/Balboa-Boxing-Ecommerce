from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryRef(ORMModel):
    id: int
    name: str
    slug: str


class CategoryOut(CategoryRef):
    product_count: int = Field(description="Productos activos en la categoría")


class VariantOut(ORMModel):
    id: int
    size: str | None = Field(None, description="Talla o peso, por ejemplo '14 oz'")
    color: str | None
    stock: int


class ProductOut(ORMModel):
    id: int
    sku: str
    name: str
    slug: str
    brand: str
    category: CategoryRef | None
    product_type: str
    price: int = Field(description="Precio en COP con IVA incluido. 0 = precio por confirmar")
    compare_at_price: int | None = Field(None, description="Precio anterior, si está en oferta")
    discount_pct: int
    image: str | None = Field(None, description="Ruta de la foto relativa a /static")
    stock: int = Field(description="Unidades disponibles sumando todas las variantes")
    available: bool = Field(description="Tiene precio y stock, se puede comprar")
    is_featured: bool


class ProductDetail(ProductOut):
    description: str
    size_info: str
    color_info: str
    material: str
    recommended_use: str
    variants: list[VariantOut]


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    pages: int


class CartItemIn(BaseModel):
    variant_id: int = Field(description="Id de la variante (ver /products/{slug})")
    quantity: int = Field(1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=99)


class CartLine(BaseModel):
    id: int
    variant_id: int
    variant_label: str
    sku: str
    name: str
    slug: str
    image: str | None
    unit_price: int
    quantity: int
    line_total: int
    stock: int


class CartOut(BaseModel):
    items: list[CartLine]
    count: int = Field(description="Unidades totales en el carrito")
    subtotal: int
    shipping_cost: int
    total: int
    free_shipping_threshold: int
    missing_for_free_shipping: int = Field(description="Cuánto falta para el envío gratis")


class Message(BaseModel):
    detail: str
