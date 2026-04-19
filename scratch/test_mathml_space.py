import latex2mathml.converter

cases = [
    r"\text{for} \quad \text{temp\_variable}",
    r"\text{for} ~ \text{temp\_variable}",
    r"\text{for} \  \text{temp\_variable}"
]

for c in cases:
    print(c)
    print(latex2mathml.converter.convert(c))
    print()
