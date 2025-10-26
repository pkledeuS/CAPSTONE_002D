import os

class LLMClient:
    """
    Por ahora genera un texto breve y legible.
    """
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "local")

    def answer(self, user_message: str, product_labels: list[str]) -> str:
        if not product_labels:
            return ("No encontré coincidencias claras.\n"
                    "¿Te gustaría ajustar el presupuesto, la categoría o la marca?")

        # Tomamos hasta 4 para no saturar (las cards muestran el resto)
        items = product_labels[:4]
        bullets = "\n".join(f"• {x}" for x in items)
        return (
            "Te recomiendo lo siguiente:\n\n"
            f"{bullets}\n\n"
            "Si quieres, comparo 2–3 modelos o filtramos por precio o marca."
        )