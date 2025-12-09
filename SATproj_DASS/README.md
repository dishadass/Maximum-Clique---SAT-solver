# Maximum Clique via SAT and Glucose

## 1. Problem Description

This project solves the **maximum clique problem** on an undirected simple graph by reducing it to **SAT** and solving the resulting CNF formula with **Glucose**.

### 1.1 Graph model

We work with graphs G = (V, E) where:

- V = {1, 2, ..., n} is the set of vertices.
- E is a set of undirected edges {u, v} with 1 ≤ u < v ≤ n.
- The graph has:
  - no self-loops: {v, v} ∉ E,
  - no multiple edges between the same pair of vertices.

The input graph is given in **DIMACS edge format**.

### 1.2 Clique definition

A **clique** in G is a subset of vertices C ⊆ V such that every pair of distinct vertices in C is adjacent:

> for all u, v in C, with u ≠ v, we have {u, v} in E.

The **size** of the clique is |C|.

The **maximum clique size** of G, usually denoted by ω(G), is:

> ω(G) = max { |C| : C ⊆ V and C is a clique in G }.

### 1.3 Problems solved by this script


#### (a) k-clique decision problem

**Input:**

- A graph G = (V, E) in DIMACS edge format.
- An integer k ≥ 1.


**Does G contain a clique of size exactly k?**

Formally: does there exist a set C ⊆ V such that:

- |C| = k, and  
- C is a clique (every two distinct vertices in C are adjacent)?

The script encodes this question as a SAT instance and calls Glucose to decide satisfiability.  
If the SAT instance is satisfiable, the script decodes the SAT model back into a concrete k-clique C.

#### (b) Maximum clique search

If no specific k is given, the script performs a simple **incremental search**:

1. Start with k = 1.
2. For each k, encode “there exists a clique of exactly size k” as SAT.
3. Call Glucose on the corresponding CNF.
4. Stop at the first k for which the SAT instance is **unsatisfiable**.

The largest k for which the SAT instance was satisfiable is then reported as the **maximum clique size** ω(G) for that graph (and the script also prints an example clique of that size).


### 1.4 Instance parameters and constraints

Each instance of the problem is determined by the following parameters.

- **Number of vertices** n  
  Given in the `p edge` line of the DIMACS file as:
  ```text
  p edge <num_vertices> <num_edges>
  ```
  We require n ≥ 1. Vertices are numbered 1, 2, ..., n.

- **Set of edges** E  
  Each edge is specified by a line of the form:
  ```text
  e u v
  ```
  where 1 ≤ u, v ≤ n. The graph is assumed to be:
  - **undirected**: the edge {u, v} is the same as {v, u},
  - **simple**: no self-loops (`u = v` lines are ignored) and no multiple edges.

- **Clique size parameter** k (for the decision version)  
  Given on the command line via:
  ```bash
  -k K
  ```
  with the intended range 1 ≤ k ≤ n.  
  The script interprets this as: “find a clique of exactly size k”.  
  If `k` is omitted, the script starts from k = 1 and increases k until UNSAT is reached (maximum clique search).



For the **k-clique decision problem**, a valid solution must satisfy all of:

1. **Cardinality constraint**  
   The selected vertex set C ⊆ V has size exactly k:

   > |C| = k.

2. **Clique constraint**  
   The selected vertices form a clique:

   > for all u, v in C, with u ≠ v, we have {u, v} in E.

For the **maximum clique search**, the same constraints apply for each tested value of k; the script keeps increasing k until these constraints can no longer be satisfied (the SAT instance becomes UNSAT). The last satisfiable k is then reported as the maximum clique size found.


## 2. CNF Encoding



### 2.1 Propositional variables

Let:

- n = number of vertices (N_VERTICES),
- k = clique size we are checking.

We introduce propositional variables:

> At(v, p)  for v in {1, ..., n} and p in {0, ..., k−1}.

which means:

- At(v, p) is true ⇔ “vertex v is assigned to clique position p”.

We think of a conceptual k × n table:

- rows = positions p = 0, 1, ..., k−1,
- columns = vertices v = 1, 2, ..., n.

The mapping to SAT variable IDs is:

> id(v, p) = p * n + v

implemented in the code as:

```python
def at_var_id(v, p, k):
    if not (0 <= p < k):
        raise ValueError(...)
    if not (1 <= v <= N_VERTICES):
        raise ValueError(...)
    return p * N_VERTICES + v
```

Thus we use exactly n * k Boolean variables.

### 2.2 Clauses

Let:

- `vertices = [1, 2, ..., N_VERTICES]`
- `positions = [0, 1, ..., k-1]`.

We encode the existence of a clique of **exactly k** using four groups of constraints.

#### (1) Each position has at least one vertex

For every position p, at least one vertex must occupy it:

> At(1, p) ∨ At(2, p) ∨ ... ∨ At(n, p)

CNF clauses:

```python
for p in range(k):
    clause = [at_var_id(v, p, k) for v in vertices]
    clause.append(0)
    cnf.append(clause)
```

#### (2) Each position has at most one vertex

No position can hold two different vertices:

> for all u < v: ¬At(u, p) ∨ ¬At(v, p)

CNF:

```python
for p in range(k):
    for u, v in all_pairs(vertices):
        cnf.append([-at_var_id(u, p, k), -at_var_id(v, p, k), 0])
```

This enforces **uniqueness** per position.

#### (3) Each vertex appears in at most one position

A vertex cannot be used in two different positions:

> for each v and all p1 < p2: ¬At(v, p1) ∨ ¬At(v, p2)

CNF:

```python
positions = list(range(k))
for v in vertices:
    for p1, p2 in all_pairs(positions):
        cnf.append([-at_var_id(v, p1, k), -at_var_id(v, p2, k), 0])
```

Together, (1), (2), and (3) enforce:

- exactly k vertices are chosen,
- they are all distinct,
- each occupies exactly one position.

#### (4) Clique constraints

Let ADJ[u] be the adjacency set of u.  
For every **non-edge** {u, v} (i.e. v not in ADJ[u]):

If u and v are both in the clique (possibly at different positions), that would violate the clique condition. So for every pair of positions p1 < p2 we add:

> ¬At(u, p1) ∨ ¬At(v, p2)  
> ¬At(v, p1) ∨ ¬At(u, p2)

CNF:

```python
for u, v in all_pairs(vertices):
    if v not in ADJ[u]:  # non-edge
        for p1, p2 in all_pairs(positions):
            cnf.append([-at_var_id(u, p1, k), -at_var_id(v, p2, k), 0])
            cnf.append([-at_var_id(v, p1, k), -at_var_id(u, p2, k), 0])
```

This forbids any satisfying assignment that chooses two non-adjacent vertices into the clique.

### 2.3 Size of the formula

- Variables: n * k
- Clauses:
  - Group (1): k clauses of length n.
  - Group (2): k * (n choose 2) binary clauses.
  - Group (3): n * (k choose 2) binary clauses.
  - Group (4): 2 * (#non-edges) * (k choose 2) binary clauses.

For dense graphs and moderate k, group (4) dominates.




## 3. Script Usage and Interface

### 3.1 Dependencies

- Python 3 .
- Glucose SAT solver compiled as:

  ```bash
  ./glucose-main/simp/glucose
  ```

Ensure the binary exists and is executable.

### 3.2 Input format: DIMACS edge format

The script reads graphs in **DIMACS edge** format, e.g.:

```text
c This is a comment line
c Another comment
p edge 4 5
e 1 2
e 1 3
e 2 3
e 2 4
e 3 4
```

- `c ...` are comments.
- `p edge <num_vertices> <num_edges>` is mandatory.
- Each `e u v` line defines an undirected edge {u, v}.

The script ignores self-loops and builds global structures:

- `N_VERTICES`
- `EDGES` (list of `(u, v)` pairs)
- `ADJ` (adjacency dictionary).

### 3.3 Command-line options

Usage:

```bash
python3 clique_sat.py [options]
```

Options:

- `-i`, `--input`  
  Path to the graph instance in DIMACS edge format.  
  Default: `graph.clq`

- `-o`, `--output`  
  Path to the CNF file (DIMACS format) to be written.  
  Default: `formula.cnf`

- `-s`, `--solver`  
  SAT solver binary to use.  
  Default: `glucose-syrup`  
  (In experiments, we call it as `./glucose-main/simp/glucose`.)

- `-v`, `--verb`  
  Solver verbosity (passed as `-verb=N` to Glucose).  
  Integer, 0 or 1. Default: `0`.

- `-k`, `--kclique`  
  If set, the script solves **only** for this clique size k (decision problem).

- `--dump-cnf-only`  
  If given, the script only constructs and writes the CNF (no solver call).  
  This is most useful together with a single fixed `-k`.

### 3.4 Modes of operation

#### Fixed k-clique mode

Example: small positive instance, k = 3

```bash
python3 clique_sat.py \
  -i small_pos.clq \
  -k 3 \
  -o small_pos_k3.cnf \
  -s ./glucose-main/simp/glucose \
  -v 1
```

Output (simplified):

- Raw Glucose output (statistics, SAT/UNSAT).
- Human-readable summary:

  ```text
  SAT: clique of size 3 found.
  Vertices in the clique: [1, 2, 3]
  ```

#### Maximum clique mode

If `-k` is omitted, the script tries k = 1, 2, … up to `N_VERTICES`:

```bash
python3 clique_sat.py \
  -i graph.clq \
  -o formula.cnf \
  -s ./glucose-main/simp/glucose
```

It prints for each k whether SAT (and the clique found).  
On the first UNSAT, it reports the maximum clique size and one corresponding clique.

Note: this can be expensive on large graphs, since it runs multiple SAT instances.

---

## 4. Description of Attached Instances

### 4.1 `small_pos.clq`

- A tiny graph intended to contain a clique of size 3.
- For k = 3, the encoding yields 12 variables and 51 clauses.

Experiment (k = 3):

- Variables: 12  
- Clauses: 51  
- Result: SAT  
- Clique: `[1, 2, 3]`  
- Glucose CPU time: ~0.0008 s  

This serves as a small, human-readable **satisfiable** test instance.

### 4.2 `small_neg.clq`

- Similar small graph, also giving 12 variables for k = 3.
- Constructed so that it **does not contain** any 3-clique.

Experiment (k = 3):

- Variables: 12  
- Clauses: 45  
- Result: UNSAT  
- Glucose reports "Solved by simplification".  
- Glucose CPU time: ~0.0008 s  

This is our small, human-readable **unsatisfiable** test instance.

### 4.3 `brock200_2.clq`

- Benchmark graph from the DIMACS maximum clique instances.
- Basic parameters:
  - Vertices: 200  
  - Edges: 9,876  
  - Known maximum clique size: ω(G) = 12.

We choose k = 12 and run the decision version:

```bash
/usr/bin/time -p python3 clique_sat.py \
  -i brock200_2.clq \
  -k 12 \
  -o brock200_2_k12.cnf \
  -s ./glucose-main/simp/glucose \
  -v 1
```

Results:

- Variables: 2,400  
- Clauses: 1,575,180  
- Result: SAT  
- Decoded clique (one example):  
  `{27, 48, 55, 70, 105, 120, 121, 135, 145, 149, 158, 183}`  

- Glucose statistics:
  - Conflicts: 293,677  
  - Decisions: 510,345  
  - Propagations: 7,440,379  
  - Glucose CPU time: ~31.5 s  

- `/usr/bin/time`:
  - `real`: ~32.5 s  
  - `user`: ~32.1 s  
  - `sys`: ~0.36 s  

This is our **nontrivial satisfiable instance**.

---

## 5. Experimental Report

All experiments were run on a Mac laptop (macOS, Python 3.14, Glucose 4.2.1).

### 5.1 Summary of experiments

| Instance       | n (vertices)    | k  | Vars  | Clauses   | Result | Glucose CPU time |
|----------------|-----------------|----|-------|-----------|--------|------------------|
| `small_pos`    | small (toy)     | 3  | 12    | 51        | SAT    | ~0.0008 s        |
| `small_neg`    | small (toy)     | 3  | 12    | 45        | UNSAT  | ~0.0008 s        |
| `brock200_2`   | 200             | 12 | 2400  | 1,575,180 | SAT    | ~31.5 s          |

Small instances are solved essentially instantly.  
The `brock200_2` instance demonstrates that the encoding and Glucose can handle a 200-vertex benchmark graph with a nontrivial clique size (12) in about half a minute.


