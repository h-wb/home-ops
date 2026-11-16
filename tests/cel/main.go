// Evaluates a ValidatingAdmissionPolicy's matchConditions and validations
// against admission requests, the way the API server combines them: every
// match condition must hold, then any false or failing validation denies
// (failurePolicy Fail). Input and output are JSON on stdin/stdout.
// Unlike the API server it does not type-check against the CRD schemas.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"cel.dev/cel-go/cel"
)

type validation struct {
	Expression string `json:"expression"`
	Message    string `json:"message"`
}

type input struct {
	MatchConditions []validation     `json:"matchConditions"`
	Validations     []validation     `json:"validations"`
	Cases           []map[string]any `json:"cases"`
}

type result struct {
	Matched bool     `json:"matched"`
	Denied  []string `json:"denied"`
}

func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fail(err)
	}
	env, err := cel.NewEnv(
		cel.Variable("object", cel.DynType),
		cel.Variable("oldObject", cel.DynType),
		cel.Variable("request", cel.DynType),
	)
	if err != nil {
		fail(err)
	}
	compile := func(v validation) cel.Program {
		ast, iss := env.Compile(v.Expression)
		if iss.Err() != nil {
			fail(fmt.Errorf("%s: %w", v.Expression, iss.Err()))
		}
		prg, err := env.Program(ast)
		if err != nil {
			fail(err)
		}
		return prg
	}
	eval := func(prg cel.Program, c map[string]any) bool {
		out, _, err := prg.Eval(c)
		return err == nil && out.Value() == true
	}
	var results []result
	for _, c := range in.Cases {
		r := result{Matched: true, Denied: []string{}}
		for _, m := range in.MatchConditions {
			if !eval(compile(m), c) {
				r.Matched = false
			}
		}
		if r.Matched {
			for _, v := range in.Validations {
				if !eval(compile(v), c) {
					r.Denied = append(r.Denied, v.Message)
				}
			}
		}
		results = append(results, r)
	}
	if err := json.NewEncoder(os.Stdout).Encode(results); err != nil {
		fail(err)
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(2)
}
