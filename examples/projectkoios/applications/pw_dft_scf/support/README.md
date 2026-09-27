# Common silicon example data

`structures/` is a minimal, bounded, reviewed representation of the structure lookup that the workflow runner needs. `MinimalStructureRepository` reads JSON and delegates scientific decoding to the maintained `UnitCellJsonCodec`.

The stable records are:

- `Si.ConventionalUnitCell`, deserialized as `ConventionalUnitCell`;
- `Si.PrimitiveUnitCell`, deserialized as `PrimitiveUnitCell`.

Each record declares `A = [a1 a2 a3]` with direct-lattice vectors as **columns**, an ordered fractional atomic basis, and an explicit physical `lattice_parameter`. `UnitCell` derives `H = lattice_parameter * A = [h1 h2 h3]`, also with vectors as columns. Calculator writers consume `H`; fractional-to-Cartesian conversion is `r = H s`.

This is not a production structure database. Revisit this filesystem boundary when Project Koios owns a durable structure repository contract; preserve the stable `structure_id` values and the maintained serialization contract.
