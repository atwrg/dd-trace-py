#include "AspectOperatorAdd.h"

/**
 * This function updates result_o object with taint information of candidate_text and/or text_to_add
 *
 * @param result_o The result object to which the aspect will be added.
 * @param candidate_text The candidate text object to which the aspect will be added.
 * @param text_to_add The text aspect to be added.
 * @param tx_taint_map The taint range map that stores taint information.
 *
 * @return A new result object with the taint information.
 */
PyObject*
add_aspect(PyObject* result_o,
           PyObject* candidate_text,
           PyObject* text_to_add,
           const TaintRangeMapTypePtr& tx_taint_map)
{
    const size_t len_candidate_text{ get_pyobject_size(candidate_text) };
    const size_t len_text_to_add{ get_pyobject_size(text_to_add) };

    if (len_text_to_add == 0 and len_candidate_text > 0) {
        return candidate_text;
    }
    if (len_text_to_add > 0 and len_candidate_text == 0 and text_to_add == result_o) {
        return text_to_add;
    }

    const auto& to_candidate_text = get_tainted_object(candidate_text, tx_taint_map);
    if (to_candidate_text and to_candidate_text->get_ranges().size() >= TaintedObject::TAINT_RANGE_LIMIT) {
        const auto& res_new_id = new_pyobject_id(result_o);
        Py_DecRef(result_o);
        // If left side is already at the maximum taint ranges, we just reuse its
        // ranges, we don't need to look at left side.
        set_tainted_object(res_new_id, to_candidate_text, tx_taint_map);
        return res_new_id;
    }

    const auto& to_text_to_add = get_tainted_object(text_to_add, tx_taint_map);
    if (!to_candidate_text and !to_text_to_add) {
        return result_o;
    }
    if (!to_text_to_add) {
        const auto& res_new_id = new_pyobject_id(result_o);
        Py_DecRef(result_o);
        set_tainted_object(res_new_id, to_candidate_text, tx_taint_map);
        return res_new_id;
    }

    auto tainted = initializer->allocate_tainted_object_copy(to_candidate_text);
    tainted->add_ranges_shifted(to_text_to_add, static_cast<RANGE_START>(len_candidate_text));
    set_tainted_object(result_o, tainted, tx_taint_map);

    return result_o;
}

/**
 * Adds aspect, override all python Add operations.
 *
 * The AST Visitor (ddtrace/appsec/_iast/_ast/visitor.py) replaces all "+" operations in Python code with this function.
 * This function takes 2 arguments. If the operation is 'a = b + c', this function should be 'a = api_add_aspect(b, c)'.
 * This function connects Python with the C++ function 'add_aspect'.
 *
 * @param self The Python extension module.
 * @param args An array of Python objects containing the candidate text and text aspect.
 * @param nargs The number of arguments in the 'args' array.
 *
 * @return A new Python object representing the result of adding the aspect to the candidate text, considering taint
 * information.
 */
PyObject*
api_add_aspect(PyObject* self, PyObject* const* args, Py_ssize_t nargs)
{
    PyObject* result_o = nullptr;

    try {
        if (nargs != 2) {
            py::set_error(PyExc_ValueError, MSG_ERROR_N_PARAMS);
            return nullptr;
        }
        PyObject* candidate_text = args[0];
        PyObject* text_to_add = args[1];

        // PyNumber_Add actually works for any type!
        result_o = PyNumber_Add(candidate_text, text_to_add);

        const auto tx_map = initializer->get_tainting_map();
        if (not tx_map or tx_map->empty()) {
            return result_o;
        }

        if (not args_are_text_and_same_type(candidate_text, text_to_add)) {
            return result_o;
        }

        // Quickly skip if both are noninterned-unicodes and not tainted
        if (is_notinterned_notfasttainted_unicode(candidate_text) &&
            is_notinterned_notfasttainted_unicode(text_to_add)) {
            return result_o;
        }

        return add_aspect(result_o, candidate_text, text_to_add, tx_map);
    } catch (const py::error_already_set& e) {
        const std::string error_message = "IAST propagation error in add_aspect. " + std::string(e.what());
        iast_taint_log_error(error_message);
        return result_o;
    } catch (const std::exception& e) {
        const std::string error_message = "IAST propagation error in add_aspect. " + std::string(e.what());
        iast_taint_log_error(error_message);
        return result_o;
    } catch (...) {
        const std::string error_message = "Unkown IAST propagation error in add_aspect. ";
        iast_taint_log_error(error_message);
        return result_o;
    }
}

PyObject*
api_add_inplace_aspect(PyObject* self, PyObject* const* args, Py_ssize_t nargs)
{
    PyObject* result_o = nullptr;

    try {
        if (nargs != 2) {
            py::set_error(PyExc_ValueError, MSG_ERROR_N_PARAMS);
            return nullptr;
        }
        PyObject* candidate_text = args[0];
        PyObject* text_to_add = args[1];

        result_o = PyNumber_InPlaceAdd(candidate_text, text_to_add);

        const auto tx_map = initializer->get_tainting_map();
        if (not tx_map or tx_map->empty()) {
            return result_o;
        }

        if (not args_are_text_and_same_type(candidate_text, text_to_add)) {
            return result_o;
        }

        // Quickly skip if both are noninterned-unicodes and not tainted
        if (is_notinterned_notfasttainted_unicode(candidate_text) &&
            is_notinterned_notfasttainted_unicode(text_to_add)) {
            return result_o;
        }
        candidate_text = add_aspect(result_o, candidate_text, text_to_add, tx_map);
        return candidate_text;
    } catch (const py::error_already_set& e) {
        const std::string error_message = "IAST propagation error in add_aspect. " + std::string(e.what());
        iast_taint_log_error(error_message);
        return result_o;
    } catch (const std::exception& e) {
        const std::string error_message = "IAST propagation error in add_aspect. " + std::string(e.what());
        iast_taint_log_error(error_message);
        return result_o;
    } catch (...) {
        const std::string error_message = "Unkown IAST propagation error in add_aspect. ";
        iast_taint_log_error(error_message);
        return result_o;
    }
}