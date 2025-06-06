""" Rivet Transpiler functions. """

import qiskit

from rivet_transpiler.stacks import get_stack_pass_manager

from rivet_transpiler.dynamical_decoupling import add_dynamical_decoupling


def transpile(circuit, backend=None, **key_arguments):

    """
    Transpile a quantum circuit with optional stack-specific optimizations.

    Parameters:
    - circuit (QuantumCircuit): The quantum circuit to be transpiled.
    - backend (BaseBackend, optional): The target backend for execution.
    - key_arguments: Additional key arguments to be passed to qiskit transpilation.

    Stack:
    - stack (str): The selected stack ('qiskit', 'qiskit_qsearch',
                                       'qiskit_qfactor_qsearch', 'qiskit_pytket')
    Pass Manager:
    - pass_manager: Custom pass manager for transpilation.

    Dynamical Decoupling Arguments:
    - dd_pulses: Dynamical decoupling pulses.
    - dd_pulses_count: Number of dynamical decoupling pulses.
    - dd_pulse_alignment: Alignment of dynamical decoupling pulses.
    - dynamical_decoupling: Enable or disable dynamical decoupling.

    Return Options:
    - return_options (bool): If True, returns a tuple (transpiled_circuit, options).
      If False (default), only the transpiled circuit is returned.

    Returns:
    - QuantumCircuit: Transpiled quantum circuit.

    Note: If 'pass_manager' is provided, it takes precedence over 'stack'.
    """

    # Parameters

    parameters = key_arguments.copy()

    parameters['backend'] = backend

    callback = parameters.pop("callback", None)
    return_options = parameters.pop('return_options', False)

    parameters_pass_manager = parameters.pop('pass_manager', None)

    dd_pulses = parameters.pop('dd_pulses', None)
    dd_pulses_count = parameters.pop('dd_pulses_count', None)
    dd_pulse_alignment = parameters.pop('dd_pulse_alignment', None)
    dynamical_decoupling = parameters.pop('dynamical_decoupling', None)

    # Pass Manager

    stack_pass_manager = get_stack_pass_manager(**parameters)

    pass_manager = parameters_pass_manager or stack_pass_manager

    # Transpile

    transpiled_circuit = pass_manager.run(circuit, callback=callback)

    # Dynamical Decoupling

    if dynamical_decoupling is True:

        transpiled_circuit = add_dynamical_decoupling(transpiled_circuit, backend,
                                                      dd_pulses, dd_pulses_count, dd_pulse_alignment)

    # Transpile Options

    if return_options is True:

        options = dict()

        options['backend'] = backend
        options['key_arguments'] = key_arguments
        options['pass_manager'] = pass_manager
        options['original_circuit'] = circuit

        return transpiled_circuit, options

    else:

        return transpiled_circuit


def transpile_chain(circuits, backend=None, **key_arguments):

    """
    Transpile a chain of quantum circuits one-by-one.

    Args:
        circuits (list of QuantumCircuit): List of input quantum circuits.
        backend: The target backend for transpilation.
        **key_arguments: Additional keyword arguments for transpilation.

    Returns:
        QuantumCircuit: The transpiled chain circuit.
    """

    # Transpile

    transpiled_circuits = []

    for circuit in circuits:

        transpiled_circuit = transpile(circuit, backend, **key_arguments)

        if transpiled_circuit.layout is None:

            key_arguments['initial_layout'] = None
            key_arguments['routing_method'] = 'none'

        else:
            full_map = get_full_map(transpiled_circuit)

            initial_layout = full_map[:circuit.num_qubits]

            key_arguments['initial_layout'] = initial_layout

        transpiled_circuits.append(transpiled_circuit)

    # Resulting Circuit

    resulting_qubits_count = max(transpiled_circuit.num_qubits
                                 for transpiled_circuit in transpiled_circuits)

    resulting_circuit = qiskit.QuantumCircuit(resulting_qubits_count)

    # Compose

    for transpiled_circuit in transpiled_circuits:

        resulting_circuit.compose(transpiled_circuit, inplace=True)

    resulting_circuit._layout = transpiled_circuit.layout

    return resulting_circuit


def transpile_right(central_circuit, right_circuit,
                    backend=None, **key_arguments):

    """
    Transpile a right quantum circuit and combine it with already transpiled central circuit.

    Args:
        central_circuit (QuantumCircuit): The central quantum circuit.
        right_circuit (QuantumCircuit): The right quantum circuit to transpile and add.
        backend: The target backend for transpilation.
        **key_arguments: Additional keyword arguments for transpilation.

    Returns:
        QuantumCircuit: The resulting quantum circuit.
    """

    # Check Layout

    if central_circuit.layout is None:

        key_arguments['initial_layout'] = None
        key_arguments['routing_method'] = 'none'

    else:
        full_map = get_full_map(central_circuit)

        key_arguments['initial_layout'] = full_map[:right_circuit.num_qubits]

    # Transpile

    transpiled_right_circuit = transpile(
        right_circuit,
        backend,
        **key_arguments)

    # Resulting Circuit

    resulting_qubits_count = max(central_circuit.num_qubits,
                                 transpiled_right_circuit.num_qubits)

    resulting_circuit = qiskit.QuantumCircuit(resulting_qubits_count)

    resulting_circuit.compose(central_circuit, inplace=True)
    resulting_circuit.compose(transpiled_right_circuit, inplace=True)

    # No Layout

    if transpiled_right_circuit.layout is None:

        return resulting_circuit

    if central_circuit.layout is None:

        resulting_circuit._layout = transpiled_right_circuit.layout

        return resulting_circuit

    # Central Routing

    if central_circuit.layout.final_layout is None:

        central_routing = list(range(central_circuit.num_qubits))

    else:
        central_routing = [central_circuit.layout.final_layout[qubit]
                           for qubit in central_circuit.qubits]

    # Right Routing

    if transpiled_right_circuit.layout.final_layout is None:

        right_routing = list(range(resulting_qubits_count))

    else:
        right_routing = [transpiled_right_circuit.layout.final_layout[qubit]
                         for qubit in transpiled_right_circuit.qubits]

    # Final Routing

    final_routing = [right_routing[qubit] for qubit in central_routing]

    # Layouts

    initial_layout = central_circuit.layout.initial_layout
    input_qubit_mapping = central_circuit.layout.input_qubit_mapping

    final_layout = qiskit.transpiler.Layout.from_intlist(
        final_routing, *resulting_circuit.qregs)

    input_qubit_count = transpiled_right_circuit.layout._input_qubit_count
    output_qubit_list = transpiled_right_circuit.layout._output_qubit_list

    # Transpile Layout

    transpile_layout = qiskit.transpiler.TranspileLayout(
        initial_layout=initial_layout,
        input_qubit_mapping=input_qubit_mapping,
        final_layout=final_layout,
        _input_qubit_count=input_qubit_count,
        _output_qubit_list=output_qubit_list)

    resulting_circuit._layout = transpile_layout

    return resulting_circuit


def transpile_left(central_circuit, left_circuit,
                   backend=None, **key_arguments):

    """
    Transpile a left quantum circuit and combine it with already transpiled central circuit.

    Args:
        central_circuit (QuantumCircuit): The central quantum circuit.
        left_circuit (QuantumCircuit): The left quantum circuit to transpile and add.
        backend: The target backend for transpilation.
        **key_arguments: Additional keyword arguments for transpilation.

    Returns:
        QuantumCircuit: The resulting quantum circuit.
    """

    # Left Initial Layout

    if central_circuit.layout is None:

        left_initial_layout = None
        key_arguments['routing_method'] = 'none'

    else:

        initial_layout = central_circuit.layout.initial_layout
        input_qubit_mapping = central_circuit.layout.input_qubit_mapping

        initial_map = [initial_layout[qubit] for qubit in input_qubit_mapping]

        left_initial_layout = initial_map[:left_circuit.num_qubits]

    # Transpile and Compose

    key_arguments['initial_layout'] = left_initial_layout

    inverted_left_circuit = left_circuit.inverse()

    transpiled_inverted_left_circuit = transpile(
        inverted_left_circuit,
        backend,
        **key_arguments)

    transpiled_left_circuit = transpiled_inverted_left_circuit.inverse()

    # Translate Left Circuit

    if backend is not None:

        basis_gates = backend.operation_names

        library = qiskit.circuit.equivalence_library.SessionEquivalenceLibrary

        custom_unroller_pass = qiskit.transpiler.passes.UnrollCustomDefinitions(
            equivalence_library=library,
            basis_gates=basis_gates)

        basis_translator_pass = qiskit.transpiler.passes.BasisTranslator(
            equivalence_library=library,
            target_basis=basis_gates)

        translator_manager = qiskit.transpiler.PassManager([
            custom_unroller_pass, basis_translator_pass])

        translated_left_circuit = translator_manager.run(transpiled_left_circuit)

    else:

        translated_left_circuit = transpiled_left_circuit

    translated_left_circuit._layout = transpiled_inverted_left_circuit.layout

    # Resulting Circuit

    resulting_qubits_count = max(central_circuit.num_qubits,
                                 translated_left_circuit.num_qubits)

    resulting_circuit = qiskit.QuantumCircuit(resulting_qubits_count)

    resulting_circuit.compose(central_circuit, inplace=True, front=True)
    resulting_circuit.compose(translated_left_circuit, inplace=True, front=True)

    # No Layout

    if translated_left_circuit.layout is None:

        return resulting_circuit

    # Left Routing

    if translated_left_circuit.layout.final_layout is None:

        left_routing = list(range(translated_left_circuit.num_qubits))

    else:
        left_routing = [translated_left_circuit.layout.final_layout[qubit]
                        for qubit in translated_left_circuit.qubits]

    # Central Routing

    if (central_circuit.layout is None or
            central_circuit.layout.final_layout is None):

        central_routing = list(range(resulting_qubits_count))

    else:
        central_routing = [central_circuit.layout.final_layout[qubit]
                           for qubit in central_circuit.qubits]

    # Final Routing

    final_routing = [central_routing[qubit] for qubit in left_routing]

    # Attributes

    input_qubit_mapping = translated_left_circuit.layout.input_qubit_mapping

    input_qubit_count = translated_left_circuit.layout._input_qubit_count
    output_qubit_list = translated_left_circuit.layout._output_qubit_list

    # Initial Layout

    initial_map = get_full_map(translated_left_circuit)

    initial_layout = translated_left_circuit.layout.initial_layout.copy()

    for virtual, physical in zip(input_qubit_mapping, initial_map):
        initial_layout[virtual] = physical

    # Final Layout

    final_layout = qiskit.transpiler.Layout.from_intlist(
        final_routing, *resulting_circuit.qregs)

    # Transpile Layout

    transpile_layout = qiskit.transpiler.TranspileLayout(
        initial_layout=initial_layout,
        input_qubit_mapping=input_qubit_mapping,
        final_layout=final_layout,
        _input_qubit_count=input_qubit_count,
        _output_qubit_list=output_qubit_list)

    resulting_circuit._layout = transpile_layout

    return resulting_circuit


def get_full_map(transpiled_circuit, verbose=False):

    """
    Get the final allocation of virtual qubits in a transpiled quantum circuit.

    Args:
        transpiled_circuit (QuantumCircuit): The transpiled quantum circuit.
        verbose (bool): Whether to print the full map calculation stages.

    Returns:
        list: The full map of qubits.
    """

    # No Layout

    if transpiled_circuit.layout is None:

        full_map = list(range(transpiled_circuit.num_qubits))

        return full_map

    # Zero Map

    input_qubit_mapping = transpiled_circuit.layout.input_qubit_mapping
    initial_layout = transpiled_circuit.layout.initial_layout
    final_layout = transpiled_circuit.layout.final_layout

    zero_map = dict(zip(input_qubit_mapping,
                        transpiled_circuit.qubits))

    # After Layout Map

    after_layout_map = [()] * transpiled_circuit.num_qubits

    for physical, in_virtual in initial_layout.get_physical_bits().items():

        out_virtual = zero_map[in_virtual]

        after_layout_map[physical] = (in_virtual, out_virtual)

    # After Routing Map

    after_routing_map = after_layout_map.copy()

    if final_layout is not None:

        for from_row, qubit in enumerate(transpiled_circuit.qubits):

            to_row = final_layout[qubit]

            from_in, from_out = after_layout_map[from_row]
            to_in, to_out = after_layout_map[to_row]

            after_routing_map[to_row] = (to_in, from_out)

    # Full Map

    full_map = []

    for out_qubit in transpiled_circuit.qubits:

        for physical, virtuals in enumerate(after_routing_map):

            in_virtual, out_virtual = virtuals

            if out_virtual is out_qubit:

                full_map.append(physical)

    # Printout

    if verbose is True:

        print("zero_map:", zero_map)
        print("after_layout_map:", after_layout_map)
        print("after_routing_map:", after_routing_map)
        print("full_map:", full_map)
        print("transpiled_circuit.layout:", transpiled_circuit.layout)

    return full_map
