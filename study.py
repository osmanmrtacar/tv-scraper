def bind_result(calculation, meta):
    study = []
    for i, val in enumerate(calculation):
        if(meta.get("plot_" + str(i))):
            plot_meta = meta.get("plot_" + str(i))
            plot_meta["title"] = plot_meta["title"] if plot_meta["title"] else "null"
            plot = {"name": plot_meta["title"], "value": str(val), "inline": True}

            study.append(plot)

    return study