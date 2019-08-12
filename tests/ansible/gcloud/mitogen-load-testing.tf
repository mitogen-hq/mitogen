variable "node-count" {
  default = 0
}

variable "preemptible" {
  default = true
}

variable "big" {
    default = false
}

provider "google" {
  project = "mitogen-load-testing"
  region  = "europe-west1"
  zone    = "europe-west1-d"
}

resource "google_compute_instance" "controller" {
  name = "ansible-controller"
  machine_type = "${var.big ? "n1-highcpu-32" : "custom-1-1024"}"

  allow_stopping_for_update = true
  can_ip_forward            = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-9"
    }
  }

  scheduling {
    preemptible       = true
    automatic_restart = false
  }

  network_interface {
    subnetwork    = "${google_compute_subnetwork.loadtest-subnet.self_link}"
    access_config = {}
  }

  provisioner "local-exec" {
    command = <<-EOF
        ip=${google_compute_instance.controller.network_interface.0.access_config.0.nat_ip};
        ssh-keygen -R $ip;
        ssh-keyscan $ip >> ~/.ssh/known_hosts;
        sed -ri -e "s/.*CONTROLLER_IP_HERE.*/    Hostname $ip/" ~/.ssh/config;
        ansible-playbook -i $ip, controller.yml
    EOF
  }
}

resource "google_compute_network" "loadtest" {
  name                    = "loadtest"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "loadtest-subnet" {
  name          = "loadtest-subnet"
  ip_cidr_range = "10.19.0.0/16"
  network       = "${google_compute_network.loadtest.id}"
}

resource "google_compute_firewall" "allow-all-in" {
  name      = "allow-all-in"
  network   = "${google_compute_network.loadtest.name}"
  direction = "INGRESS"

  allow {
    protocol = "all"
  }
}

resource "google_compute_firewall" "allow-all-out" {
  name      = "allow-all-out"
  network   = "${google_compute_network.loadtest.name}"
  direction = "EGRESS"

  allow {
    protocol = "all"
  }
}

resource "google_compute_route" "route-nodes-via-controller" {
  name                   = "route-nodes-via-controller"
  dest_range             = "0.0.0.0/0"
  network                = "${google_compute_network.loadtest.name}"
  next_hop_instance      = "${google_compute_instance.controller.self_link}"
  next_hop_instance_zone = "${google_compute_instance.controller.zone}"
  priority               = 800
  tags                   = ["node"]
}

resource "google_compute_instance_template" "node" {
  name         = "node"
  tags         = ["node"]
  machine_type = "custom-1-1024"

  scheduling {
    preemptible       = "${var.preemptible}"
    automatic_restart = false
  }

  disk {
    source_image = "debian-cloud/debian-9"
    auto_delete  = true
    boot         = true
  }

  network_interface {
    subnetwork = "${google_compute_subnetwork.loadtest-subnet.self_link}"
  }
}

#
# Compute Engine tops out at 1000 VMs per group
#

resource "google_compute_instance_group_manager" "nodes-a" {
  name = "nodes-a"

  base_instance_name = "node"
  instance_template  = "${google_compute_instance_template.node.self_link}"
  target_size        = "${var.node-count / 4}"
}

resource "google_compute_instance_group_manager" "nodes-b" {
  name = "nodes-b"

  base_instance_name = "node"
  instance_template  = "${google_compute_instance_template.node.self_link}"
  target_size        = "${var.node-count / 4}"
}

resource "google_compute_instance_group_manager" "nodes-c" {
  name = "nodes-c"

  base_instance_name = "node"
  instance_template  = "${google_compute_instance_template.node.self_link}"
  target_size        = "${var.node-count / 4}"
}

resource "google_compute_instance_group_manager" "nodes-d" {
  name = "nodes-d"

  base_instance_name = "node"
  instance_template  = "${google_compute_instance_template.node.self_link}"
  target_size        = "${var.node-count / 4}"
}
