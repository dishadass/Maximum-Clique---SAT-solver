import subprocess
from argparse import ArgumentParser

N_VERTICES = 0
EDGES = []
ADJ = {}


def load_instance(input_file_name):
    """
    Load a graph in DIMACS 'edge' format:

        c comments...
        p edge <num_vertices> <num_edges>
        e u v
        e u v
        ...

    Sets global N_VERTICES, EDGES, ADJ.
    """
    global N_VERTICES, EDGES, ADJ

    N_VERTICES = None
    EDGES = []

    with open(input_file_name, "r") as f:
        raw_lines = [line.strip() for line in f]

    for line in raw_lines:
        if not line or line.startswith("c"):
            continue

        tokens = line.split()
        if tokens[0] == "p":
            if len(tokens) < 4 or tokens[1] != "edge":
                raise ValueError("Only DIMACS 'p edge <num_vertices> <num_edges>' format is supported.")
            try:
                N_VERTICES = int(tokens[2])
            except ValueError as e:
                raise ValueError("Invalid number of vertices in 'p' line.") from e
            break

    if N_VERTICES is None:
        raise ValueError("No valid 'p edge' header line found in the input file.")

    for line in raw_lines:
        if not line or line.startswith("c"):
            continue

        tokens = line.split()
        tag = tokens[0]

        if tag == "e":
            if len(tokens) < 3:
                raise ValueError(f"Malformed edge line: {line!r}")
            try:
                u = int(tokens[1])
                v = int(tokens[2])
            except ValueError as e:
                raise ValueError(f"Non-integer vertex id in edge line: {line!r}") from e

            if u == v:
                continue

            if u > v:
                u, v = v, u

            EDGES.append((u, v))

    ADJ = {vertex: set() for vertex in range(1, N_VERTICES + 1)}
    for u, v in EDGES:
        ADJ[u].add(v)
        ADJ[v].add(u)

    return (N_VERTICES, EDGES)


def at_var_id(v, p, k):
    """
    Encode At(v, p): vertex v is at clique position p (0..k-1)
    as a SAT variable id in 1..(N_VERTICES * k).

    We conceptually think of a k x N_VERTICES table of variables:

        row p (0-based)  -> clique position
        column v (1-based) -> vertex id

    Variables are numbered row by row, starting from 1.
    """
    if not (0 <= p < k):
        raise ValueError(f"Position p={p} is out of range [0, {k-1}].")
    if not (1 <= v <= N_VERTICES):
        raise ValueError(f"Vertex v={v} is out of range [1, {N_VERTICES}].")

    row_offset = p * N_VERTICES
    var_id = row_offset + v

    return var_id


def encode_k_clique(k):
    """
    Encode 'there exists a clique of size EXACTLY k'
    in the global graph (N_VERTICES, ADJ).

    Variables: At(v,p) for v in {1..N_VERTICES}, p in {0..k-1}.

    Returns:
        (cnf, nr_vars)
    where:
        cnf     = list of clauses, each clause is a list of ints ending with 0
        nr_vars = total number of SAT variables
    """
    cnf = []
    vertices = list(range(1, N_VERTICES + 1))

    def all_pairs(items):
        """Yield all ordered pairs (i, j) with i < j from a sequence."""
        n = len(items)
        for idx in range(n):
            for jdx in range(idx + 1, n):
                yield items[idx], items[jdx]

    for p in range(k):
        clause = [at_var_id(v, p, k) for v in vertices]
        clause.append(0)
        cnf.append(clause)

    for p in range(k):
        for u, v in all_pairs(vertices):
            cnf.append([-at_var_id(u, p, k), -at_var_id(v, p, k), 0])

    positions = list(range(k))
    for v in vertices:
        for p1, p2 in all_pairs(positions):
            cnf.append([-at_var_id(v, p1, k), -at_var_id(v, p2, k), 0])

    for u, v in all_pairs(vertices):
        if v not in ADJ[u]:
            for p1, p2 in all_pairs(positions):
                cnf.append([-at_var_id(u, p1, k), -at_var_id(v, p2, k), 0])
                cnf.append([-at_var_id(v, p1, k), -at_var_id(u, p2, k), 0])

    nr_vars = N_VERTICES * k
    return cnf, nr_vars


def write_cnf_to_file(cnf, nr_vars, output_name):
    """
    Write CNF to a DIMACS file.

    The format is:
        p cnf <nr_vars> <nr_clauses>
        <lit1> <lit2> ... 0
        ...
    """
    nr_clauses = len(cnf)
    lines = []
    header = " ".join(["p", "cnf", str(nr_vars), str(nr_clauses)])
    lines.append(header + "\n")
    for clause in cnf:
        literal_strings = [str(lit) for lit in clause]
        lines.append(" ".join(literal_strings) + "\n")
    with open(output_name, "w") as f:
        f.writelines(lines)


def call_solver(output_name, solver_name, verbosity):
    """
    Call Glucose (or another SAT solver) on the DIMACS CNF formula.

    Returns the CompletedProcess object.
    """
    if solver_name.startswith("./"):
        solver_cmd = solver_name
    else:
        solver_cmd = "./" + solver_name

    cmd = [
        solver_cmd,
        "-model",
        f"-verb={verbosity}",
        output_name,
    ]

    return subprocess.run(cmd, stdout=subprocess.PIPE)


def parse_model(result):
    """
    Parse the model from the solver output.
    Returns a list 'model' where model[i] is the literal for variable i+1,
    or None if UNSAT.
    """
    if result.returncode == 20:
        return None

    raw_output = result.stdout.decode("utf-8")
    model_literals = []

    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] != "v":
            continue

        tokens = stripped.split()
        for t in tokens[1:]:
            try:
                lit = int(t)
            except ValueError:
                continue
            model_literals.append(lit)

    model = [lit for lit in model_literals if lit != 0]

    return model


def extract_stats(result):
    """
    Extract selected statistics lines from Glucose output.
    Returns a list of lines (strings).
    """
    output = result.stdout.decode("utf-8")
    keywords = {"conflicts", "decisions", "propagations", "CPU time"}

    def is_stats_line(line: str) -> bool:
        line = line.strip()
        if not (line.startswith("c ") or line.startswith("c|") or line.startswith("c |")):
            return False
        return any(key in line for key in keywords)

    return [line.strip() for line in output.splitlines() if is_stats_line(line)]


def decode_clique(model, k):
    """
    Given a model and clique size k, decode which vertices are in the clique.
    Uses the fact that model[var_id-1] is the assignment for variable var_id.
    """
    clique_vertices = set()

    for v in range(1, N_VERTICES + 1):
        in_clique = False
        for p in range(k):
            var_id = at_var_id(v, p, k)
            if model[var_id - 1] > 0:
                in_clique = True
                break
        if in_clique:
            clique_vertices.add(v)

    return sorted(clique_vertices)


def solve_for_fixed_k(k, output_name, solver_name, verbosity, dump_only=False):
    """
    Encode the k-clique problem, optionally only dump CNF,
    or call the solver and decode the result.
    """
    cnf, nr_vars = encode_k_clique(k)
    write_cnf_to_file(cnf, nr_vars, output_name)

    if dump_only:
        print(f"CNF for k={k} written to {output_name}. (solver not called)")
        return

    result = call_solver(output_name, solver_name, verbosity)

    def print_raw_output(proc_result):
        print("========== Solver raw output ==========")
        text = proc_result.stdout.decode("utf-8")
        for line in text.splitlines():
            print(line)
        print("=======================================\n")

    print_raw_output(result)

    rc = result.returncode

    if rc == 20:
        print(f"UNSAT: no clique of size {k}.")
        return

    if rc != 10:
        print(f"Solver returned unexpected code: {rc}")
        return

    model = parse_model(result)
    clique_vertices = decode_clique(model, k)

    print("##################################################################")
    print("###########[ Human readable result of the clique problem ]########")
    print("##################################################################")
    print()
    print(f"SAT: clique of size {k} found.")
    print("Vertices in the clique:", clique_vertices)
    print()

    stats_lines = extract_stats(result)
    if stats_lines:
        print("---------- Solver statistics (from Glucose) ----------")
        for line in stats_lines:
            print(line)
        print("------------------------------------------------------")


def solve_max_clique(output_name, solver_name, verbosity, dump_only=False):
    """
    Incrementally search for the maximum clique size by testing k = 1, 2, ...
    For each k, encode and write a CNF instance and (unless dump_only=True)
    invoke the SAT solver. Stops when the first UNSAT result is encountered.

    NOTE: with dump_only=True this will only keep the CNF for the last k
    (since the same output file is reused each time).
    """
    best_k = 0
    best_clique = []

    def print_banner(k_value):
        print("====================================================")
        print(f"Trying clique size k = {k_value}")
        print("====================================================")

    def show_raw_output(proc_result):
        print("========== Solver raw output ==========")
        text = proc_result.stdout.decode("utf-8")
        for ln in text.splitlines():
            print(ln)
        print("=======================================\n")

    for k in range(1, N_VERTICES + 1):
        print_banner(k)

        cnf, nr_vars = encode_k_clique(k)
        write_cnf_to_file(cnf, nr_vars, output_name)

        if dump_only:
            print(f"(dump-only) CNF for k={k} written to {output_name}")
            continue

        result = call_solver(output_name, solver_name, verbosity)
        show_raw_output(result)

        rc = result.returncode

        if rc == 20:
            print(f"No clique of size {k}. Maximum clique size is {best_k}.")
            break

        if rc != 10:
            print(f"Solver returned unexpected code: {rc}")
            break

        model = parse_model(result)
        clique_vertices = decode_clique(model, k)

        best_k = k
        best_clique = clique_vertices

        print(f"SAT: clique of size {k} found. Vertices: {clique_vertices}")
        print()

        stats_lines = extract_stats(result)
        if stats_lines:
            print("---------- Solver statistics (from Glucose) ----------")
            for ln in stats_lines:
                print(ln)
            print("------------------------------------------------------")

    print()
    print("##################################################################")
    print("###########[ Final maximum clique result ]########################")
    print("##################################################################")
    print()
    print(f"Maximum clique size: {best_k}")
    print("Vertices in a maximum clique:", best_clique)


def build_arg_parser():
    parser = ArgumentParser(description="Encode and solve the k-clique / max-clique problem via SAT.")

    parser.add_argument(
        "-i", "--input",
        type=str,
        default="graph.clq",
        help="Graph instance file in DIMACS edge format."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="formula.cnf",
        help="Output file for the DIMACS CNF formula."
    )
    parser.add_argument(
        "-s", "--solver",
        type=str,
        default="glucose-syrup",
        help="SAT solver binary to be used (e.g. glucose-syrup)."
    )
    parser.add_argument(
        "-v", "--verb",
        type=int,
        default=0,
        choices=range(0, 2),
        help="Verbosity of the SAT solver (0 or 1)."
    )
    parser.add_argument(
        "-k", "--kclique",
        type=int,
        default=None,
        help=(
            "If set, solve only for a clique of this size k. "
            "If omitted, search for a maximum clique by incrementing k."
        ),
    )
    parser.add_argument(
        "--dump-cnf-only",
        action="store_true",
        help="Only construct and write the CNF to file; do not call the SAT solver."
    )

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    load_instance(args.input)

    if args.kclique is None:
        solve_max_clique(
            output_name=args.output,
            solver_name=args.solver,
            verbosity=args.verb,
            dump_only=args.dump_cnf_only,
        )
    else:
        solve_for_fixed_k(
            k=args.kclique,
            output_name=args.output,
            solver_name=args.solver,
            verbosity=args.verb,
            dump_only=args.dump_cnf_only,
        )


if __name__ == "__main__":
    main()
