
# Expand disk size to max

[03:22]Quantum (Virgil): So I'm really confused as to why the tigera-operator pod is just stuck in an "Eviction loop"
[03:27]Quantum (Virgil): Found this:
Image
[03:27]Quantum (Virgil): Per: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/
[03:39]budimanjojo: your master node is low on disk
[03:49]Quantum (Virgil): Oof
[03:50]Quantum (Virgil): How much space should allocate to my master nodes?
[03:50]Quantum (Virgil): I gave them 256 GB
[03:50]Quantum (Virgil): Assuming that's not enough then
[03:50]Quantum (Virgil): I added another 256 GB (since they are virtualized masters), so they're not at 512 GB
[04:02]budimanjojo: I'm not sure now, 256GB should be plenty. and if it's only happening in tigera-operator, I think u should check their default helm values, maybe there's a switch
[04:09]Quantum (Virgil): The strangest thing is that this wasn't happening at all before
[04:10]Quantum (Virgil): It just randomly started while I was trying to enable a few new cluster services
[04:23]Quantum (Virgil): Trying to just try and reinstall the cluster
[04:39]Quantum (Virgil): Cluster reinstalled successfully, so now I'm just waiting on everything to start back up
[04:41]Quantum (Virgil): So far, not seeing tigera-operator eviction looping
[07:44]onedr0p ᵈᵉᵛⁱⁿ: check the root disk size
[07:46]onedr0p ᵈᵉᵛⁱⁿ: it's very easy in the fedora installer to miss setting the lvm size on the root disk
[07:46]onedr0p ᵈᵉᵛⁱⁿ: you'll need to do something like lvresize -l +100%FREE --resizefs /dev/mapper/ubuntu--vg-ubuntu--lv to get the volume expanded.
