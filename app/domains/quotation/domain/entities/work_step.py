class WorkStep():

    def __init__(
        self,
        step_id: int,
        item_id: int,
        sequence: int,
        layers: int,
        description: str,
        note: str
    ):
        self.step_id = step_id
        self.item_id = item_id
        self.sequence = sequence
        self.layers = layers
        self.description = description
        self.note = note
