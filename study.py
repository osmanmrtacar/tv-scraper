def bind_result(calculation, meta):
    study = []
    for i, val in enumerate(calculation):
        if(meta.get("plot_" + str(i))):
            plot_meta = meta.get("plot_" + str(i))
            plot_meta["title"] = plot_meta["title"] if plot_meta["title"] else "null"
            plot = {"name": plot_meta["title"], "value": str(val), "inline": True}
            if("plot_" + str(i) == "plot_0" or "plot_" + str(i) == "plot_1" 
                or "plot_" + str(i) == "plot_13" or "plot_" + str(i) == "plot_14"
                    or "plot_" + str(i) == "plot_15" or "plot_" + str(i) == "plot_16"):
                    
                if val != 0:
                    study.append(plot)

            

    return study