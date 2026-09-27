# SCF terminal comparison

`PwDftScfEnergyAlignmentKind` distinguishes native from explicit reference-zero treatment. `PwDftScfComparisonInterpretation` bounds the resulting scientific claim. `PwDftScfEnergyAlignmentDeclaration` records policy before a result exists, and `PwDftScfEnergyAlignment` binds a result to that treatment. `PwDftScfComparisonRequest` orders two aligned results and cites input-alignment evidence. `PwDftScfComparator` produces an immutable `PwDftScfComparisonAnalysis`.

The comparator reports rather than hides native-energy and sampling differences. It does not assert absolute-energy equivalence between calculators.
